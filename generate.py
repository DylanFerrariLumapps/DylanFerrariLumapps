"""Render the profile cards in assets/ from the GitHub API.

Needs a token in GH_TOKEN that can read the private repos you contribute to.
Only aggregate numbers end up in the SVGs, never private repo names.
"""

import base64
import json
import math
import os
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from xml.sax.saxutils import escape

DISPLAY_NAME = "Dylan Ferrari"
TAGLINE = "Backend engineer · LumApps"
WIDTH = 840

# Green checks: a passing pipeline.
TEXT = "#e6f4ea"
MUTED = "#8aa394"
DIM = "#4d6355"
ACCENT = "#3fb950"
ACCENT_SOFT = "#7ee787"
PANEL = "#101712"
BG_TOP = "#0d1a12"
BG_BOTTOM = "#080b09"
BORDER = "#1d2e23"
QUIET = "#1c2a21"
HEAT = ["#14201a", "#1b4d2e", "#26a641", "#39d353", "#8cffa0"]
WEEKDAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

SANS = "'Inter', 'Segoe UI', -apple-system, Helvetica, Arial, sans-serif"
MONO = "'JetBrains Mono', 'SF Mono', Menlo, Consolas, monospace"
STYLE = f"""<style>
text {{ font-family: {SANS}; }}
.mono {{ font-family: {MONO}; }}
.blink {{ animation: blink 1.1s step-end infinite; }}
@keyframes blink {{ 50% {{ opacity: 0; }} }}
.wave {{ animation: wave 7s ease-in-out infinite; }}
@keyframes wave {{ 0%, 24%, 100% {{ transform: scaleY(1); }} 12% {{ transform: scaleY(1.4); }} }}
@media (prefers-reduced-motion: reduce) {{ .wave, .blink {{ animation: none; }} }}
</style>"""

ASSETS = Path(__file__).parent / "assets"
TOKEN = os.environ["GH_TOKEN"]

QUERY = """
query {
  viewer {
    login avatarUrl createdAt
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date weekday contributionCount } }
      }
    }
    repositoriesContributedTo(
      first: 50
      contributionTypes: [COMMIT, PULL_REQUEST, PULL_REQUEST_REVIEW]
      includeUserRepositories: true
    ) {
      totalCount
    }
  }
}
"""

SEARCH_QUERY = """
query($search: String!, $cursor: String) {
  search(query: $search, type: ISSUE, first: 50, after: $cursor) {
    pageInfo { hasNextPage endCursor }
    nodes { ... on PullRequest { %s } }
  }
}
"""
AUTHORED_FIELDS = "createdAt mergedAt additions deletions files(first: 100) { nodes { path additions } }"
REVIEWED_FIELDS = 'createdAt reviews(author: "%s", first: 1) { nodes { submittedAt } }'

# Code and specs only: JSON is mostly cassettes and fixtures, Markdown is docs.
LANGUAGES_BY_EXTENSION = {
    "py": "Python",
    "yaml": "YAML",
    "yml": "YAML",
    "sql": "SQL",
    "ts": "TypeScript",
    "tsx": "TypeScript",
    "js": "JavaScript",
    "jsx": "JavaScript",
    "sh": "Shell",
    "html": "HTML",
    "tf": "Terraform",
    "go": "Go",
}


def request(url: str, body: dict | None = None) -> bytes:
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers={"Authorization": f"bearer {TOKEN}"})
    with urllib.request.urlopen(req) as resp:
        return resp.read()


def fetch_viewer() -> dict:
    return json.loads(request("https://api.github.com/graphql", {"query": QUERY}))["data"]["viewer"]


def search_pull_requests(search: str, fields: str) -> list[dict]:
    pull_requests: list[dict] = []
    variables = {"search": search, "cursor": None}
    while True:
        body = {"query": SEARCH_QUERY % fields, "variables": variables}
        result = json.loads(request("https://api.github.com/graphql", body))["data"]["search"]
        pull_requests += result["nodes"]
        if not result["pageInfo"]["hasNextPage"]:
            return pull_requests
        variables["cursor"] = result["pageInfo"]["endCursor"]


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def format_duration(hours: float) -> str:
    if hours < 1:
        return f"{hours * 60:.0f} min"
    if hours < 48:
        return f"{hours:.1f} h"
    return f"{hours / 24:.1f} days"


def compute_top_languages(merged: list[dict]) -> list[tuple[str, float]]:
    # Lines added in my merged PRs, so only what I actually shipped counts.
    shares: dict[str, int] = defaultdict(int)
    for pull_request in merged:
        for file in pull_request["files"]["nodes"]:
            language = LANGUAGES_BY_EXTENSION.get(file["path"].rsplit(".", 1)[-1])
            if language:
                shares[language] += file["additions"]
    grand_total = sum(shares.values()) or 1
    top = sorted(shares.items(), key=lambda item: item[1], reverse=True)[:3]
    return [(name, share / grand_total) for name, share in top]


def compute_longest_streak(days: list[dict]) -> int:
    # Weekends neither extend nor break a streak.
    longest = run = 0
    for day in days:
        if day["weekday"] in (0, 6):
            continue
        run = run + 1 if day["contributionCount"] else 0
        longest = max(longest, run)
    return longest


def wrap_svg(height: int, body: str, defs: str = "") -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" '
        f'viewBox="0 0 {WIDTH} {height}">{STYLE}<defs>'
        '<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="{BG_TOP}"/><stop offset="1" stop-color="{BG_BOTTOM}"/></linearGradient>'
        '<radialGradient id="flare" cx="0.12" cy="0" r="0.9">'
        f'<stop offset="0" stop-color="{ACCENT}" stop-opacity="0.22"/>'
        f'<stop offset="1" stop-color="{ACCENT}" stop-opacity="0"/></radialGradient>'
        '<linearGradient id="edge" x1="0" x2="1">'
        f'<stop offset="0" stop-color="{ACCENT}" stop-opacity="0.7"/>'
        f'<stop offset="0.5" stop-color="{BORDER}"/><stop offset="1" stop-color="{BORDER}"/></linearGradient>'
        '<pattern id="grid" width="22" height="22" patternUnits="userSpaceOnUse">'
        '<path d="M22 0H0V22" fill="none" stroke="#ffffff" stroke-opacity="0.035"/></pattern>'
        '<filter id="glow" x="-50%" y="-50%" width="200%" height="200%">'
        '<feGaussianBlur stdDeviation="3" result="b"/>'
        '<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>'
        f"{defs}</defs>"
        f'<rect width="{WIDTH}" height="{height}" rx="16" fill="url(#bg)"/>'
        f'<rect width="{WIDTH}" height="{height}" rx="16" fill="url(#flare)"/>'
        f'<rect width="{WIDTH}" height="{height}" rx="16" fill="url(#grid)"/>'
        f'<rect x="0.5" y="0.5" width="{WIDTH - 1}" height="{height - 1}" rx="15.5" fill="none" stroke="url(#edge)"/>'
        f"{body}</svg>"
    )


def render_check_line(y: int, checks: list[str]) -> str:
    items = "".join(
        f'<tspan fill="{ACCENT}">✓</tspan> {escape(check)}' + ("   " if index < len(checks) - 1 else "")
        for index, check in enumerate(checks)
    )
    return f'<text class="mono" x="236" y="{y}" fill="{TEXT}" font-size="13" xml:space="preserve">{items}</text>'


def render_hero(viewer: dict, repo_count: int, languages: list[tuple[str, float]],
                opened: int, merged: int, reviewed: int) -> str:
    avatar = base64.b64encode(request(viewer["avatarUrl"] + "&s=320")).decode()
    defs = (
        '<clipPath id="avatar"><rect x="40" y="70" width="168" height="168" rx="18"/></clipPath>'
        '<linearGradient id="name" x1="0" x2="1">'
        f'<stop offset="0" stop-color="{TEXT}"/><stop offset="1" stop-color="{ACCENT_SOFT}"/></linearGradient>'
        '<filter id="halo" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="18"/></filter>'
        # Grayscale, then map shadows to the background green and highlights to mint.
        '<filter id="duotone"><feColorMatrix type="matrix" values="'
        '.3 .59 .11 0 0 .3 .59 .11 0 0 .3 .59 .11 0 0 0 0 0 1 0"/>'
        '<feComponentTransfer><feFuncR type="table" tableValues="0.02 0.06 0.66"/>'
        '<feFuncG type="table" tableValues="0.05 0.32 1"/><feFuncB type="table" tableValues="0.03 0.1 0.7"/>'
        '</feComponentTransfer></filter>'
        '<pattern id="scanlines" width="4" height="4" patternUnits="userSpaceOnUse">'
        '<rect width="4" height="1.5" fill="#000000" fill-opacity="0.35"/></pattern>'
    )
    window = (
        f'<rect x="1" y="1" width="{WIDTH - 2}" height="36" rx="15" fill="{PANEL}"/>'
        f'<rect x="1" y="22" width="{WIDTH - 2}" height="15" fill="{PANEL}"/>'
        f'<line x1="1" x2="{WIDTH - 1}" y1="37" y2="37" stroke="{BORDER}"/>'
        '<circle cx="24" cy="19" r="5.5" fill="#ff5f57"/><circle cx="42" cy="19" r="5.5" fill="#febc2e"/>'
        '<circle cx="60" cy="19" r="5.5" fill="#28c840"/>'
        f'<text class="mono" x="{WIDTH / 2}" y="23" fill="{MUTED}" font-size="12" text-anchor="middle">'
        f'{viewer["login"].lower()}@github: ~/profile</text>'
    )
    portrait = (
        f'<rect x="48" y="78" width="152" height="152" rx="18" fill="{ACCENT}" opacity="0.35" filter="url(#halo)"/>'
        '<g clip-path="url(#avatar)">'
        f'<image href="data:image/png;base64,{avatar}" x="40" y="70" width="168" height="168" filter="url(#duotone)"/>'
        '<rect x="40" y="70" width="168" height="168" fill="url(#scanlines)"/></g>'
        f'<rect x="40.5" y="70.5" width="167" height="167" rx="18" fill="none" stroke="{ACCENT}" stroke-opacity="0.7"/>'
    )
    language_summary = " · ".join(f"{name.lower()} {share:.0%}" for name, share in languages if share >= 0.01)
    terminal = (
        f'<text class="mono" x="236" y="86" fill="{ACCENT_SOFT}" font-size="13"><tspan fill="{DIM}">~ $</tspan> whoami</text>'
        f'<text x="234" y="128" fill="url(#name)" font-size="40" font-weight="800" letter-spacing="-1">'
        f"{escape(DISPLAY_NAME)}</text>"
        f'<text x="236" y="156" fill="{TEXT}" fill-opacity="0.8" font-size="16" font-weight="500">{escape(TAGLINE)}</text>'
        f'<text class="mono" x="236" y="190" fill="{ACCENT_SOFT}" font-size="13"><tspan fill="{DIM}">~ $</tspan> make tests</text>'
        + render_check_line(212, [f"{merged} PRs merged", f"{reviewed} reviews given", f"{merged / opened:.0%} merge rate"])
        + render_check_line(232, [language_summary, f"{repo_count} repos since {viewer['createdAt'][:4]}"])
        + f'<text class="mono" x="236" y="256" fill="{DIM}" font-size="13">~ $ '
        f'<tspan class="blink" fill="{ACCENT}">▍</tspan></text>'
    )
    return wrap_svg(280, window + portrait + terminal, defs)


def render_sparkline(x: float, y: float, width: float, height: float, values: list[int]) -> str:
    peak = max(values) or 1
    step = width / (len(values) - 1)
    points = [(x + i * step, y + height - height * value / peak) for i, value in enumerate(values)]
    line = " ".join(f"{px:.1f},{py:.1f}" for px, py in points)
    area = f"M{x},{y + height} L" + " L".join(f"{px:.1f},{py:.1f}" for px, py in points) + f" L{x + width},{y + height}Z"
    return (
        f'<path d="{area}" fill="url(#spark)"/>'
        f'<polyline points="{line}" fill="none" stroke="{ACCENT}" stroke-width="1.8" '
        'stroke-linejoin="round" stroke-linecap="round"/>'
    )


def tile_x(index: int) -> int:
    return 24 + index * 202


def render_tile(index: int, label: str, value: str, content: str) -> str:
    x = tile_x(index)
    return (
        f'<g>'
        f'<rect x="{x}" y="20" width="186" height="132" rx="14" fill="{PANEL}" fill-opacity="0.85" stroke="{BORDER}"/>'
        f'<rect x="{x + 18}" y="20" width="28" height="2.5" rx="1.25" fill="{ACCENT}"/>'
        f'<text class="mono" x="{x + 18}" y="50" fill="{MUTED}" font-size="10.5" letter-spacing="1.2">{label}</text>'
        f'<text x="{x + 16}" y="94" fill="{TEXT}" font-size="36" font-weight="800" letter-spacing="-1">{value}</text>'
        f"{content}</g>"
    )


def render_caption(index: int, text: str) -> str:
    return f'<text x="{tile_x(index) + 18}" y="126" fill="{MUTED}" font-size="12.5">{escape(text)}</text>'


def render_donut(index: int, rate: float) -> str:
    cx = tile_x(index) + 150
    circumference = 2 * math.pi * 20
    return (
        f'<circle cx="{cx}" cy="80" r="20" fill="none" stroke="{BORDER}" stroke-width="6"/>'
        f'<circle cx="{cx}" cy="80" r="20" transform="rotate(-90 {cx} 80)" fill="none" stroke="{ACCENT}" '
        f'stroke-width="6" stroke-linecap="round" stroke-dasharray="{circumference * rate:.1f} {circumference:.1f}" '
        'filter="url(#glow)"/>'
    )


def render_stats(viewer: dict, opened: int, merged: int, reviewed: int, repo_count: int) -> str:
    calendar = viewer["contributionsCollection"]["contributionCalendar"]
    weekly = [sum(day["contributionCount"] for day in week["contributionDays"]) for week in calendar["weeks"]]
    rate = merged / opened if opened else 0
    tiles = (
        render_tile(0, "CONTRIBUTIONS", f"{calendar['totalContributions']:,}",
                    render_sparkline(tile_x(0) + 18, 106, 150, 30, weekly))
        + render_tile(1, "PULL REQUESTS", f"{opened:,}", render_caption(1, f"opened across {repo_count} repos"))
        + render_tile(2, "CODE REVIEWS", f"{reviewed:,}", render_caption(2, "teammates' PRs reviewed"))
        + render_tile(3, "MERGE RATE", f"{rate:.0%}",
                      render_caption(3, f"{merged:,} of {opened:,} merged") + render_donut(3, rate))
    )
    defs = (
        '<linearGradient id="spark" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{ACCENT}" stop-opacity="0.35"/>'
        f'<stop offset="1" stop-color="{ACCENT}" stop-opacity="0"/></linearGradient>'
    )
    return wrap_svg(172, tiles, defs)


def render_heatmap(viewer: dict) -> str:
    calendar = viewer["contributionsCollection"]["contributionCalendar"]
    weeks = calendar["weeks"]
    days = [day for week in weeks for day in week["contributionDays"]]
    peak = max(day["contributionCount"] for day in days) or 1

    cells = ""
    months = ""
    # Skip the first month's label when only a week or two of it is shown.
    second_month = date.fromisoformat(weeks[2]["contributionDays"][0]["date"]).strftime("%b")
    last_label_week = -4
    previous_month = None
    for week_index, week in enumerate(weeks):
        x = 62 + week_index * 14
        month = date.fromisoformat(week["contributionDays"][0]["date"]).strftime("%b")
        if (
            month != previous_month
            and (week_index > 0 or month == second_month)
            and week_index - last_label_week >= 4
            and week_index < len(weeks) - 2
        ):
            months += f'<text class="mono" x="{x}" y="76" fill="{MUTED}" font-size="10">{month}</text>'
            last_label_week = week_index
        previous_month = month
        for day in week["contributionDays"]:
            count = day["contributionCount"]
            level = 0 if count == 0 else min(4, 1 + int(3 * count / peak))
            glow = ' filter="url(#glow)"' if level == 4 else ""
            cells += (
                f'<rect x="{x}" '
                f'y="{86 + day["weekday"] * 14}" width="11" height="11" rx="2.5" fill="{HEAT[level]}"{glow}/>'
            )
    weekday_labels = "".join(
        f'<text class="mono" x="24" y="{95 + row * 14}" fill="{DIM}" font-size="10">{name}</text>'
        for row, name in [(1, "Mon"), (3, "Wed"), (5, "Fri")]
    )

    active_days = sum(1 for day in days if day["contributionCount"])
    best = max(days, key=lambda day: day["contributionCount"])
    by_weekday = [0] * 7
    for day in days:
        by_weekday[day["weekday"]] += day["contributionCount"]
    busiest = WEEKDAYS[by_weekday.index(max(by_weekday))]
    facts = [
        ("ACTIVE DAYS", f"{active_days} of {len(days)}"),
        ("LONGEST STREAK", f"{compute_longest_streak(days)} workdays"),
        ("BEST DAY", f"{best['contributionCount']} on {date.fromisoformat(best['date']):%b %-d}"),
        ("BUSIEST DAY", f"{busiest}s"),
    ]
    footer = f'<line x1="24" x2="{WIDTH - 24}" y1="198" y2="198" stroke="{BORDER}"/>'
    for index, (label, value) in enumerate(facts):
        x = 24 + index * 150
        footer += (
            f'<text class="mono" x="{x}" y="222" fill="{MUTED}" font-size="10" letter-spacing="1.2">{label}</text>'
            f'<text x="{x}" y="244" fill="{TEXT}" font-size="16" font-weight="700">{value}</text>'
        )
    legend = f'<text class="mono" x="{WIDTH - 134}" y="240" fill="{DIM}" font-size="10" text-anchor="end">less</text>'
    for level, color in enumerate(HEAT):
        legend += f'<rect x="{WIDTH - 128 + level * 14}" y="231" width="11" height="11" rx="2.5" fill="{color}"/>'
    legend += f'<text class="mono" x="{WIDTH - 24}" y="240" fill="{DIM}" font-size="10" text-anchor="end">more</text>'

    header = (
        f'<text x="24" y="42" fill="{TEXT}" font-size="18" font-weight="700">Activity</text>'
        f'<text class="mono" x="{WIDTH - 24}" y="42" fill="{MUTED}" font-size="12" text-anchor="end">'
        f'<tspan fill="{ACCENT_SOFT}">{calendar["totalContributions"]:,}</tspan> contributions · last 12 months</text>'
    )
    return wrap_svg(268, header + months + weekday_labels + cells + footer + legend)


def shade(color: str, factor: float) -> str:
    channels = [int(color[i : i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{min(255, int(channel * factor)):02x}" for channel in channels)


def render_skyline(viewer: dict) -> str:
    calendar = viewer["contributionsCollection"]["contributionCalendar"]
    weeks = calendar["weeks"]
    days = [day for week in weeks for day in week["contributionDays"]]
    peak_day = max(days, key=lambda day: day["contributionCount"])
    peak = peak_day["contributionCount"] or 1

    # Oblique projection: weeks run right and slightly up, weekdays run right and down.
    week_step, day_step, origin, size = (13.0, -3.6), (6.0, 7.0), (40.0, 330.0), 0.8

    def project(week: float, weekday: float, height: float = 0) -> tuple[float, float]:
        return (
            origin[0] + week * week_step[0] + weekday * day_step[0],
            origin[1] + week * week_step[1] + weekday * day_step[1] - height,
        )

    def polygon(points: list[tuple[float, float]], fill: str, extra: str = "") -> str:
        coordinates = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
        return f'<polygon points="{coordinates}" fill="{fill}"{extra}/>'

    floor = [project(-0.4, -0.4), project(len(weeks), -0.4), project(len(weeks), 7), project(-0.4, 7)]
    shapes = polygon(floor, "#ffffff", f' fill-opacity="0.025" stroke="{BORDER}"')
    by_position = {
        (week_index, day["weekday"]): day["contributionCount"]
        for week_index, week in enumerate(weeks)
        for day in week["contributionDays"]
    }
    # Painter's order: the back row and the right-most weeks first.
    for weekday in range(7):
        for week_index in reversed(range(len(weeks))):
            if (week_index, weekday) not in by_position:
                continue
            count = by_position[(week_index, weekday)]
            level = 0 if count == 0 else min(4, 1 + int(3 * count / peak))
            color = HEAT[level] if level else QUIET
            height = 2 if count == 0 else 6 + 64 * count / peak
            w, d = week_index, weekday
            # Each column rests at its real height; the wave only lifts it briefly as it passes.
            base_x, base_y = project(w + size / 2, d + size / 2)
            column = polygon(
                [project(w, d), project(w, d + size), project(w, d + size, height), project(w, d, height)],
                shade(color, 0.45),
            )
            column += polygon(
                [project(w, d + size), project(w + size, d + size),
                 project(w + size, d + size, height), project(w, d + size, height)],
                shade(color, 0.7),
            )
            glow = ' filter="url(#glow)"' if level == 4 else ""
            column += polygon(
                [project(w, d, height), project(w + size, d, height),
                 project(w + size, d + size, height), project(w, d + size, height)],
                shade(color, 1.15),
                glow,
            )
            if count == 0:
                shapes += column
                continue
            shapes += (
                f'<g class="wave" style="transform-origin:{base_x:.1f}px {base_y:.1f}px;'
                f'animation-delay:{week_index * 0.07:.2f}s">{column}</g>'
            )

    header = (
        f'<text x="24" y="42" fill="{TEXT}" font-size="18" font-weight="700">Contribution skyline</text>'
        f'<text class="mono" x="{WIDTH - 24}" y="42" fill="{MUTED}" font-size="12" text-anchor="end">'
        f'peak <tspan fill="{ACCENT_SOFT}">{peak}</tspan> on {date.fromisoformat(peak_day["date"]):%b %-d}</text>'
    )
    first, last = date.fromisoformat(days[0]["date"]), date.fromisoformat(days[-1]["date"])
    start, end = project(0, 7.6), project(len(weeks), 7.6)
    axis = (
        f'<text class="mono" x="{start[0]:.0f}" y="{start[1] + 14:.0f}" fill="{DIM}" font-size="10">'
        f"{first:%b %Y}</text>"
        f'<text class="mono" x="{end[0]:.0f}" y="{end[1] + 14:.0f}" fill="{DIM}" font-size="10" '
        f'text-anchor="end">{last:%b %Y}</text>'
    )
    return wrap_svg(400, header + shapes + axis)


def render_header(title: str, detail: str) -> str:
    return (
        f'<text x="24" y="42" fill="{TEXT}" font-size="18" font-weight="700">{title}</text>'
        f'<text class="mono" x="{WIDTH - 24}" y="42" fill="{MUTED}" font-size="12" text-anchor="end">{detail}</text>'
    )


def render_sizes(merged: list[dict]) -> str:
    sizes = sorted(pull_request["additions"] + pull_request["deletions"] for pull_request in merged)
    buckets = [("XS", "under 10 lines", 10), ("S", "10 – 99", 100), ("M", "100 – 399", 400),
               ("L", "400 – 999", 1000), ("XL", "1,000+", math.inf)]
    counts = [0] * len(buckets)
    for size in sizes:
        counts[next(index for index, (_, _, limit) in enumerate(buckets) if size < limit)] += 1
    widest = max(counts) or 1
    rows = ""
    for index, ((name, span, _), count) in enumerate(zip(buckets, counts)):
        y = 80 + index * 32
        width = 520 * count / widest
        rows += (
            f'<text class="mono" x="24" y="{y + 13}" fill="{TEXT}" font-size="13" font-weight="700">{name}</text>'
            f'<text class="mono" x="62" y="{y + 13}" fill="{MUTED}" font-size="11">{span}</text>'
            f'<rect x="190" y="{y}" width="520" height="18" rx="5" fill="#ffffff" fill-opacity="0.03"/>'
            f'<rect x="190" y="{y}" width="{max(width, 4):.1f}" height="18" rx="5" fill="url(#bar)"/>'
            f'<text class="mono" x="{WIDTH - 24}" y="{y + 13}" fill="{TEXT}" font-size="12" text-anchor="end">'
            f'{count} <tspan fill="{MUTED}">{count / len(sizes):.0%}</tspan></text>'
        )
    detail = f'median <tspan fill="{ACCENT_SOFT}">{sizes[len(sizes) // 2]}</tspan> lines · {len(sizes)} merged PRs'
    defs = (
        '<linearGradient id="bar" x1="0" x2="1">'
        f'<stop offset="0" stop-color="{HEAT[2]}"/><stop offset="1" stop-color="{ACCENT}"/></linearGradient>'
    )
    return wrap_svg(256, render_header("PR size profile", detail) + rows, defs)


def render_duration_panel(x: int, label: str, hours: list[float]) -> str:
    hours = sorted(hours)
    buckets = [("< 1h", 1), ("< 1d", 24), ("< 3d", 72), ("< 1w", 168), ("1w+", math.inf)]
    colors = [HEAT[4], HEAT[3], HEAT[2], HEAT[1], QUIET]
    counts = [0] * len(buckets)
    for value in hours:
        counts[next(index for index, (_, limit) in enumerate(buckets) if value < limit)] += 1
    panel = (
        f'<rect x="{x}" y="64" width="384" height="168" rx="14" fill="{PANEL}" fill-opacity="0.85" stroke="{BORDER}"/>'
        f'<rect x="{x + 18}" y="64" width="28" height="2.5" rx="1.25" fill="{ACCENT}"/>'
        f'<text class="mono" x="{x + 18}" y="94" fill="{MUTED}" font-size="10.5" letter-spacing="1.2">{label}</text>'
        f'<text x="{x + 16}" y="136" fill="{TEXT}" font-size="34" font-weight="800" letter-spacing="-1">'
        f"{format_duration(hours[len(hours) // 2])}</text>"
        f'<text x="{x + 18}" y="158" fill="{MUTED}" font-size="12.5">median over {len(hours)} PRs · '
        f"p75 {format_duration(hours[len(hours) * 3 // 4])}</text>"
        f'<clipPath id="clip{x}"><rect x="{x + 18}" y="174" width="348" height="10" rx="5"/></clipPath>'
    )
    segments = ""
    offset = x + 18.0
    for count, color in zip(counts, colors):
        width = 348 * count / len(hours)
        segments += f'<rect x="{offset:.1f}" y="174" width="{width:.1f}" height="10" fill="{color}"/>'
        offset += width
    legend = ""
    for index, ((name, _), count, color) in enumerate(zip(buckets, counts, colors)):
        lx = x + 18 + index * 70
        legend += (
            f'<rect x="{lx}" y="198" width="8" height="8" rx="2" fill="{color}"/>'
            f'<text class="mono" x="{lx + 13}" y="206" fill="{TEXT}" font-size="10.5">{escape(name)} '
            f'<tspan fill="{MUTED}">{count / len(hours):.0%}</tspan></text>'
        )
    return panel + f'<g clip-path="url(#clip{x})">{segments}</g>' + legend


def render_turnaround(merged: list[dict], reviewed: list[dict]) -> str:
    merge_hours = [
        (parse_time(pr["mergedAt"]) - parse_time(pr["createdAt"])).total_seconds() / 3600 for pr in merged
    ]
    review_hours = [
        (parse_time(pr["reviews"]["nodes"][0]["submittedAt"]) - parse_time(pr["createdAt"])).total_seconds() / 3600
        for pr in reviewed
        if pr["reviews"]["nodes"]
    ]
    body = (
        render_header("Review turnaround", "all time")
        + render_duration_panel(24, "MY PRS · OPENED → MERGED", merge_hours)
        + render_duration_panel(432, "TEAMMATES' PRS · OPENED → MY REVIEW", review_hours)
    )
    return wrap_svg(252, body)


def render_pulse(authored: list[dict], reviewed: list[dict]) -> str:
    today = date.today()
    months = [(today.year + (today.month - 12 + i - 1) // 12, (today.month - 12 + i - 1) % 12 + 1) for i in range(1, 13)]
    opened = [0] * 12
    reviews = [0] * 12
    for pr in authored:
        created = parse_time(pr["createdAt"])
        if (created.year, created.month) in months:
            opened[months.index((created.year, created.month))] += 1
    for pr in reviewed:
        if pr["reviews"]["nodes"]:
            submitted = parse_time(pr["reviews"]["nodes"][0]["submittedAt"])
            if (submitted.year, submitted.month) in months:
                reviews[months.index((submitted.year, submitted.month))] += 1

    left, right, top, bottom = 56, WIDTH - 32, 74, 200
    ceiling = max(opened + reviews) or 1
    step = (right - left) / 11

    def points(values: list[int]) -> list[tuple[float, float]]:
        return [(left + i * step, bottom - (bottom - top) * value / ceiling) for i, value in enumerate(values)]

    grid = ""
    for fraction in (0, 0.5, 1):
        y = bottom - (bottom - top) * fraction
        grid += (
            f'<line x1="{left}" x2="{right}" y1="{y:.1f}" y2="{y:.1f}" stroke="#ffffff" stroke-opacity="0.06"/>'
            f'<text class="mono" x="{left - 10}" y="{y + 4:.1f}" fill="{DIM}" font-size="10" text-anchor="end">'
            f"{ceiling * fraction:.0f}</text>"
        )
    labels = "".join(
        f'<text class="mono" x="{left + i * step:.1f}" y="{bottom + 22}" fill="{MUTED}" font-size="10" '
        f'text-anchor="middle">{date(year, month, 1):%b}</text>'
        for i, (year, month) in enumerate(months)
    )
    opened_points, review_points = points(opened), points(reviews)
    area = (
        f"M{left},{bottom} L" + " L".join(f"{x:.1f},{y:.1f}" for x, y in opened_points) + f" L{right},{bottom}Z"
    )
    lines = (
        f'<path d="{area}" fill="url(#pulse)"/>'
        f'<polyline points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in opened_points)}" fill="none" '
        f'stroke="{ACCENT}" stroke-width="2.2" stroke-linejoin="round" filter="url(#glow)"/>'
        f'<polyline points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in review_points)}" fill="none" '
        f'stroke="{ACCENT_SOFT}" stroke-width="1.8" stroke-dasharray="5 4" stroke-linejoin="round"/>'
    )
    dots = "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{BG_TOP}" stroke="{ACCENT}" stroke-width="1.8"/>'
        for x, y in opened_points
    ) + "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.5" fill="{ACCENT_SOFT}"/>' for x, y in review_points
    )
    legend = (
        f'<tspan fill="{ACCENT}">●</tspan> PRs opened  '
        f'<tspan fill="{ACCENT_SOFT}">●</tspan> PRs reviewed'
    )
    defs = (
        '<linearGradient id="pulse" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{ACCENT}" stop-opacity="0.3"/>'
        f'<stop offset="1" stop-color="{ACCENT}" stop-opacity="0"/></linearGradient>'
    )
    return wrap_svg(244, render_header("Monthly pulse", legend) + grid + labels + lines + dots, defs)


def render_milestones(authored: list[dict], merged: list[dict]) -> str:
    merged = sorted(merged, key=lambda pr: pr["mergedAt"])
    events = [("FIRST PR", parse_time(min(pr["createdAt"] for pr in authored)), "opened")]
    events += [
        (f"{count}TH MERGED PR", parse_time(merged[count - 1]["mergedAt"]), "merged")
        for count in (100, 250, 500, 1000)
        if len(merged) >= count
    ]
    by_week: dict[date, int] = defaultdict(int)
    for pr in merged:
        merged_on = parse_time(pr["mergedAt"]).date()
        by_week[merged_on - timedelta(days=merged_on.weekday())] += 1
    best_week, best_count = max(by_week.items(), key=lambda item: item[1])
    events.append(("BIGGEST WEEK", datetime.combine(best_week, datetime.min.time()), f"{best_count} PRs merged"))
    events.sort(key=lambda event: event[1].replace(tzinfo=None))

    start = events[0][1].replace(tzinfo=None)
    span = (datetime.now() - start).total_seconds() or 1
    left, right, axis = 80, WIDTH - 80, 130
    track = (
        f'<line x1="{left}" x2="{right}" y1="{axis}" y2="{axis}" stroke="url(#track)" stroke-width="3" '
        'stroke-linecap="round"/>'
    )
    nodes = ""
    for index, (label, moment, note) in enumerate(events):
        x = left + (right - left) * (moment.replace(tzinfo=None) - start).total_seconds() / span
        above = index % 2 == 0
        label_y, date_y = (axis - 44, axis - 24) if above else (axis + 34, axis + 54)
        # Keep labels near the ends inside the card.
        anchor, text_x = "middle", x
        if x < left + 90:
            anchor, text_x = "start", x - 10
        elif x > right - 90:
            anchor, text_x = "end", x + 10
        nodes += (
            f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{axis}" y2="{axis + (-14 if above else 14)}" stroke="{BORDER}"/>'
            f'<circle cx="{x:.1f}" cy="{axis}" r="7" fill="{BG_TOP}" stroke="{ACCENT}" stroke-width="2.5" filter="url(#glow)"/>'
            f'<text class="mono" x="{text_x:.1f}" y="{label_y}" fill="{MUTED}" font-size="10" letter-spacing="1.1" '
            f'text-anchor="{anchor}">{label}</text>'
            f'<text x="{text_x:.1f}" y="{date_y}" fill="{TEXT}" font-size="14" font-weight="700" text-anchor="{anchor}">'
            f'{moment:%b %-d, %Y} <tspan fill="{MUTED}" font-weight="400" font-size="12">· {note}</tspan></text>'
        )
    defs = (
        f'<linearGradient id="track" gradientUnits="userSpaceOnUse" x1="{left}" x2="{right}" y1="0" y2="0">'
        f'<stop offset="0" stop-color="{HEAT[1]}"/><stop offset="1" stop-color="{ACCENT}"/></linearGradient>'
    )
    return wrap_svg(220, render_header("Milestones", f"{len(merged)} PRs merged so far") + track + nodes, defs)


def main() -> None:
    viewer = fetch_viewer()
    login = viewer["login"]
    repos = viewer["repositoriesContributedTo"]
    authored = search_pull_requests(f"type:pr author:{login}", AUTHORED_FIELDS)
    merged = [pr for pr in authored if pr["mergedAt"]]
    reviewed = search_pull_requests(f"type:pr reviewed-by:{login} -author:{login}", REVIEWED_FIELDS % login)
    ASSETS.mkdir(exist_ok=True)
    (ASSETS / "hero.svg").write_text(render_hero(
        viewer, repos["totalCount"], compute_top_languages(merged), len(authored), len(merged), len(reviewed)
    ))
    (ASSETS / "stats.svg").write_text(render_stats(viewer, len(authored), len(merged), len(reviewed), repos["totalCount"]))
    (ASSETS / "heatmap.svg").write_text(render_heatmap(viewer))
    (ASSETS / "skyline.svg").write_text(render_skyline(viewer))
    (ASSETS / "pulse.svg").write_text(render_pulse(authored, reviewed))
    (ASSETS / "sizes.svg").write_text(render_sizes(merged))
    (ASSETS / "turnaround.svg").write_text(render_turnaround(merged, reviewed))
    (ASSETS / "milestones.svg").write_text(render_milestones(authored, merged))


if __name__ == "__main__":
    main()
