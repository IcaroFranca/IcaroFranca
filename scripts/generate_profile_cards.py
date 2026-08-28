#!/usr/bin/env python3
"""Generate dependency-free SVG cards from GitHub's public API."""

from __future__ import annotations

import html
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


USERNAME = "IcaroFranca"
ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
API = "https://api.github.com"
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
COLORS = {
    "background": "#0d1117",
    "border": "#30363d",
    "primary": "#22d3ee",
    "secondary": "#06b6d4",
    "muted": "#8b949e",
    "text": "#e6edf3",
    "empty": "#161b22",
}


def api_json(path: str) -> object:
    request = urllib.request.Request(
        f"{API}{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "IcaroFranca-profile-cards",
            "X-GitHub-Api-Version": "2022-11-28",
            **({"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}),
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def safe_api_json(path: str, default: object) -> object:
    try:
        return api_json(path)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        return default


def paginated(path: str, max_pages: int = 10) -> list[dict]:
    separator = "&" if "?" in path else "?"
    items: list[dict] = []
    for page in range(1, max_pages + 1):
        batch = safe_api_json(f"{path}{separator}per_page=100&page={page}", [])
        if not isinstance(batch, list):
            break
        items.extend(item for item in batch if isinstance(item, dict))
        if len(batch) < 100:
            break
    return items


def escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def svg_shell(width: int, height: int, content: str, title: str) -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
  <title id="title">{escape(title)}</title>
  <desc id="desc">Dados públicos atualizados do perfil GitHub de {USERNAME}</desc>
  <defs>
    <linearGradient id="accent" x1="0" x2="1">
      <stop offset="0" stop-color="#0e7490" />
      <stop offset="1" stop-color="#22d3ee" />
    </linearGradient>
    <style>
      .title {{ fill: {COLORS['primary']}; font: 600 18px 'Segoe UI', Ubuntu, sans-serif; }}
      .value {{ fill: {COLORS['text']}; font: 700 25px 'Segoe UI', Ubuntu, sans-serif; }}
      .label {{ fill: {COLORS['muted']}; font: 400 12px 'Segoe UI', Ubuntu, sans-serif; }}
      .small {{ fill: {COLORS['muted']}; font: 400 11px 'Segoe UI', Ubuntu, sans-serif; }}
    </style>
  </defs>
  <rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="12" fill="{COLORS['background']}" stroke="{COLORS['border']}" />
  <rect x="0" y="0" width="5" height="{height}" rx="3" fill="url(#accent)" />
{content}
</svg>
"""


def write_svg(name: str, source: str) -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    (ASSETS / name).write_text(source, encoding="utf-8", newline="\n")


def years_on_github(created_at: str) -> int:
    created = datetime.fromisoformat(created_at.replace("Z", "+00:00")).date()
    today = date.today()
    years = today.year - created.year
    if (today.month, today.day) < (created.month, created.day):
        years -= 1
    return max(years, 0)


def overview_card(profile: dict, repos: list[dict], public_commits: int) -> str:
    stars = sum(int(repo.get("stargazers_count", 0)) for repo in repos)
    metrics = [
        (len(repos), "repositórios públicos"),
        (profile.get("followers", 0), "seguidores"),
        (public_commits, "commits públicos · 1 ano"),
        (years_on_github(profile["created_at"]), "anos no GitHub"),
    ]
    blocks = []
    positions = [(36, 72), (270, 72), (36, 142), (270, 142)]
    for (value, label), (x, y) in zip(metrics, positions):
        blocks.append(f'  <text x="{x}" y="{y}" class="value">{escape(value)}</text>')
        blocks.append(f'  <text x="{x}" y="{y + 20}" class="label">{escape(label)}</text>')
    content = '  <text x="24" y="35" class="title">GitHub em números</text>\n' + "\n".join(blocks)
    return svg_shell(495, 190, content, "Resumo do GitHub")


def language_card(language_bytes: Counter[str]) -> str:
    total = sum(language_bytes.values()) or 1
    top = language_bytes.most_common(5)
    palette = ["#22d3ee", "#06b6d4", "#0891b2", "#155e75", "#164e63"]
    rows = ['  <text x="24" y="35" class="title">Linguagens mais usadas</text>']
    y = 65
    for index, (language, amount) in enumerate(top):
        percentage = amount / total * 100
        bar_width = max(4, round(250 * percentage / max(top[0][1] / total * 100, 1)))
        rows.extend(
            [
                f'  <circle cx="29" cy="{y - 4}" r="5" fill="{palette[index]}" />',
                f'  <text x="42" y="{y}" class="label" style="fill:{COLORS["text"]};font-weight:600">{escape(language)}</text>',
                f'  <text x="465" y="{y}" text-anchor="end" class="label">{percentage:.1f}%</text>',
                f'  <rect x="145" y="{y - 10}" width="250" height="7" rx="3.5" fill="{COLORS["empty"]}" />',
                f'  <rect x="145" y="{y - 10}" width="{bar_width}" height="7" rx="3.5" fill="{palette[index]}" />',
            ]
        )
        y += 25
    if not top:
        rows.append('  <text x="24" y="85" class="label">Nenhuma linguagem pública encontrada.</text>')
    return svg_shell(495, 190, "\n".join(rows), "Linguagens mais usadas")


def flexibase_activity_card() -> str:
    """Render the authenticated Flexibase activity snapshot collected locally."""
    commits = 239
    pull_requests = 112
    code_reviews = 0
    issues = 0
    systems = 7
    total = commits + pull_requests + code_reviews + issues
    maximum = max(commits, pull_requests, code_reviews, issues, 1)
    center_x, center_y, radius = 750, 145, 90

    points = [
        (center_x, center_y - radius * code_reviews / maximum),
        (center_x + radius * issues / maximum, center_y),
        (center_x, center_y + radius * pull_requests / maximum),
        (center_x - radius * commits / maximum, center_y),
    ]
    polygon = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    commit_share = round(commits / total * 100)
    pr_share = round(pull_requests / total * 100)

    rows = [
        '  <text x="24" y="35" class="title">Atuação na Flexibase · últimos 12 meses</text>',
        '  <rect x="24" y="52" width="215" height="31" rx="7" fill="#161b22" stroke="#30363d" />',
        '  <circle cx="42" cy="67.5" r="10" fill="url(#accent)" />',
        '  <text x="42" y="72" text-anchor="middle" style="fill:#ffffff;font:700 12px Segoe UI,Ubuntu,sans-serif">F</text>',
        '  <text x="59" y="72" style="fill:#e6edf3;font:600 13px Segoe UI,Ubuntu,sans-serif">@Flexibase-Projects</text>',
        f'  <text x="24" y="128" class="value">{total}</text>',
        '  <text x="24" y="148" class="label">atividades localizadas</text>',
        f'  <text x="24" y="184" style="fill:#e6edf3;font:700 16px Segoe UI,Ubuntu,sans-serif">{commits}</text>',
        '  <text x="63" y="184" class="label">commits</text>',
        f'  <text x="150" y="184" style="fill:#e6edf3;font:700 16px Segoe UI,Ubuntu,sans-serif">{pull_requests}</text>',
        '  <text x="188" y="184" class="label">pull requests</text>',
        f'  <text x="322" y="184" style="fill:#e6edf3;font:700 16px Segoe UI,Ubuntu,sans-serif">{systems}</text>',
        '  <text x="339" y="184" class="label">sistemas</text>',
        '  <text x="24" y="222" class="small">Maior atuação: Portal de Chamados e SGQ</text>',
        '  <text x="24" y="244" class="small">Também: PDF · SGE · DASH · TPM · FoccoAPI</text>',
        '  <text x="24" y="264" class="small">Snapshot autenticado em 28 ago 2026</text>',
        '  <line x1="470" y1="28" x2="470" y2="252" stroke="#30363d" />',
    ]

    for fraction in (0.25, 0.5, 0.75, 1.0):
        r = radius * fraction
        ring = (
            f"{center_x},{center_y-r:.1f} "
            f"{center_x+r:.1f},{center_y} "
            f"{center_x},{center_y+r:.1f} "
            f"{center_x-r:.1f},{center_y}"
        )
        rows.append(f'  <polygon points="{ring}" fill="none" stroke="#21262d" stroke-width="1" />')

    rows.extend(
        [
            f'  <line x1="{center_x}" y1="{center_y-radius}" x2="{center_x}" y2="{center_y+radius}" stroke="#30363d" />',
            f'  <line x1="{center_x-radius}" y1="{center_y}" x2="{center_x+radius}" y2="{center_y}" stroke="#30363d" />',
            f'  <polygon points="{polygon}" fill="#22d3ee" fill-opacity="0.28" stroke="#22d3ee" stroke-width="2" />',
            *[
                f'  <circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="#e6edf3" stroke="#22d3ee" stroke-width="2" />'
                for x, y in points
            ],
            f'  <text x="{center_x}" y="34" text-anchor="middle" class="label">{round(code_reviews / total * 100)}% · Code review</text>',
            f'  <text x="940" y="150" text-anchor="end" class="label">Issues · {round(issues / total * 100)}%</text>',
            f'  <text x="{center_x}" y="267" text-anchor="middle" class="label">{pr_share}% · Pull requests</text>',
            f'  <text x="555" y="150" class="label">{commit_share}% · Commits</text>',
        ]
    )
    return svg_shell(1000, 280, "\n".join(rows), "Atividade de desenvolvimento na Flexibase")


def streaks(day_counts: Counter[date], today: date) -> tuple[int, int]:
    days = [today - timedelta(days=offset) for offset in range(365, -1, -1)]
    longest = current_run = 0
    for day in days:
        if day_counts[day] > 0:
            current_run += 1
            longest = max(longest, current_run)
        else:
            current_run = 0

    cursor = today
    if day_counts[cursor] == 0:
        cursor -= timedelta(days=1)
    current = 0
    while day_counts[cursor] > 0:
        current += 1
        cursor -= timedelta(days=1)
    return current, longest


def contribution_card(day_counts: Counter[date]) -> str:
    today = date.today()
    start = today - timedelta(days=364)
    start -= timedelta(days=start.weekday() + 1 if start.weekday() < 6 else 0)
    days = [start + timedelta(days=offset) for offset in range((today - start).days + 1)]
    while len(days) % 7:
        days.append(days[-1] + timedelta(days=1))

    max_count = max(day_counts.values(), default=1)
    colors = [COLORS["empty"], "#083344", "#155e75", "#0891b2", "#22d3ee"]

    def level(count: int) -> int:
        if count <= 0:
            return 0
        ratio = count / max_count
        return 1 if ratio <= 0.20 else 2 if ratio <= 0.45 else 3 if ratio <= 0.70 else 4

    cells = []
    cell, gap = 10, 3
    graph_x, graph_y = 250, 60
    for index, day in enumerate(days):
        week, weekday = divmod(index, 7)
        count = day_counts[day] if day <= today else 0
        cells.append(
            f'  <rect x="{graph_x + week * (cell + gap)}" y="{graph_y + weekday * (cell + gap)}" width="{cell}" height="{cell}" rx="2" fill="{colors[level(count)]}"><title>{day.isoformat()}: {count} commit(s)</title></rect>'
        )

    total = sum(count for day, count in day_counts.items() if day >= today - timedelta(days=364))
    current, longest = streaks(day_counts, today)
    details = [
        '  <text x="24" y="35" class="title">Atividade pública · últimos 12 meses</text>',
        f'  <text x="28" y="80" class="value">{total}</text>',
        '  <text x="28" y="100" class="label">commits públicos</text>',
        f'  <text x="28" y="137" class="label"><tspan style="fill:{COLORS["text"]};font-weight:700">{current} dias</tspan> · sequência atual</text>',
        f'  <text x="28" y="158" class="label"><tspan style="fill:{COLORS["text"]};font-weight:700">{longest} dias</tspan> · maior sequência</text>',
        *cells,
        f'  <text x="965" y="163" text-anchor="end" class="small">menos  ■ ■ ■ ■ ■  mais</text>',
    ]
    return svg_shell(1000, 180, "\n".join(details), "Atividade pública no GitHub")


def fetch_repository_details(repo: dict, since: str) -> tuple[Counter[str], Counter[date]]:
    full_name = repo["full_name"]
    languages_data = safe_api_json(f"/repos/{full_name}/languages", {})
    languages = Counter(languages_data if isinstance(languages_data, dict) else {})
    encoded_since = urllib.parse.quote(since)
    commits = paginated(
        f"/repos/{full_name}/commits?author={USERNAME}&since={encoded_since}",
        max_pages=10,
    )
    days: Counter[date] = Counter()
    for commit in commits:
        timestamp = commit.get("commit", {}).get("author", {}).get("date")
        if timestamp:
            days[datetime.fromisoformat(timestamp.replace("Z", "+00:00")).date()] += 1
    return languages, days


def main() -> int:
    profile = api_json(f"/users/{USERNAME}")
    repositories = [
        repo
        for repo in paginated(f"/users/{USERNAME}/repos?type=owner&sort=updated")
        if not repo.get("fork") and not repo.get("archived")
    ]
    since = (datetime.now(timezone.utc) - timedelta(days=365)).isoformat().replace("+00:00", "Z")
    language_bytes: Counter[str] = Counter()
    day_counts: Counter[date] = Counter()

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(fetch_repository_details, repo, since) for repo in repositories]
        for future in as_completed(futures):
            languages, days = future.result()
            language_bytes.update(languages)
            day_counts.update(days)

    write_svg("github-overview.svg", overview_card(profile, repositories, sum(day_counts.values())))
    write_svg("languages.svg", language_card(language_bytes))
    write_svg("contributions.svg", contribution_card(day_counts))
    write_svg("flexibase-activity.svg", flexibase_activity_card())
    print(f"Generated 4 cards for {USERNAME} from {len(repositories)} public repositories.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
