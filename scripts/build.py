"""Builds the animated SVG cards for the flxnsee profile README.

Runs on the standard library only. Pulls live data from the GitHub API
(GraphQL contribution calendar when a token is present, public events
otherwise) and writes a dark and a light variant of every card.

    python scripts/build.py --out dist
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from xml.sax.saxutils import escape

# ── profile config ──────────────────────────────────────────────────────────

USER = os.environ.get("GH_USER", "flxnsee")
NAME = "Artem Kostenko"
ROLES = [
    "backend developer",
    "C# & Python, mostly",
    "Telegram bot smith",
    "game dev on weekends",
    "CS2 enjoyer",
]

# (repo, blurb, icon). The sixth inventory slot is always the locked one.
PROJECTS = [
    ("claude-code-rpc", "Claude Code as a live Discord Rich Presence card, with a pixel tamagotchi cat that reacts to the session.", "cat"),
    ("faceit-analyzer", "Turns a Faceit CS2 match history into K/D trends, per-map stats and the weak spots the official site hides.", "crosshair"),
    ("parcel-tracker-bot", "Telegram bot that keeps an eye on AliExpress parcels and pings you when they move.", "parcel"),
    ("fit-chat-bot", "Telegram chat bot for the FIT student community, built on aiogram and MongoDB.", "chat"),
    ("flansee", "HABITAT OS: my portfolio as a living ASCII habitat you can wander through.", "sprout"),
]

# Stack as Kyiv metro lines. Station names that match a GitHub language get a
# live "share of code" caption under them.
METRO = [
    ("M1", "Backend", "red", ["C#", ".NET", "EF Core", "Python", "aiogram", "Go"], False),
    ("M2", "Web", "blue", ["TypeScript", "JavaScript", "React", "Next.js", "Tailwind"], False),
    ("M3", "Data & tools", "green", ["MSSQL", "MongoDB", "SQLite", "Git", "Arch + Hyprland"], False),
    ("M4", "Game & 3D", "yellow", ["Unity", "Unreal Engine", "Blender"], True),
]

# ── themes ──────────────────────────────────────────────────────────────────

THEMES = {
    "dark": dict(
        bg="#0d0c14", card="#14121d", border="#2a2638", text="#f4efe6", muted="#8e88a3",
        peach="#ffb4a2", lav="#c9b6ff", mint="#9fe2c0", sky="#8ccfff", butter="#ffe08a", rose="#ff8fb1",
        red="#ff6b6b", blue="#5aa9ff", green="#4fd1a1", yellow="#ffd34d",
        cat="#f3d9c4", cat_eye="#1b1626", station="#14121d", river="#1d2a44",
    ),
    "light": dict(
        bg="#f7f3ec", card="#fffdf8", border="#e6dfd2", text="#1d1a24", muted="#7a7386",
        peach="#e9785e", lav="#7f63d9", mint="#2f9e6e", sky="#2f84c9", butter="#c99a1a", rose="#d94f7f",
        red="#e5484d", blue="#2f7fe0", green="#1fa37a", yellow="#e8b416",
        cat="#3b3350", cat_eye="#fff4e6", station="#fffdf8", river="#dcebfa",
    ),
}

SANS = "'Segoe UI', Inter, -apple-system, 'Helvetica Neue', Arial, sans-serif"
MONO = "'JetBrains Mono', 'SFMono-Regular', Consolas, 'Liberation Mono', monospace"
LANG_COLORS = {
    "Python": "#3572A5", "C#": "#178600", "Go": "#00ADD8", "TypeScript": "#3178c6",
    "JavaScript": "#f1e05a", "HTML": "#e34c26", "CSS": "#663399", "C++": "#f34b7d",
}


def base_css(t: dict, extra: str = "") -> str:
    return f"""<style>
.sans{{font-family:{SANS}}} .mono{{font-family:{MONO}}}
.fg{{fill:{t['text']}}} .mu{{fill:{t['muted']}}}
@keyframes blink{{0%,92%,100%{{transform:scaleY(1)}}95%{{transform:scaleY(.1)}}}}
@keyframes floaty{{0%,100%{{transform:translateY(0)}}50%{{transform:translateY(-4px)}}}}
@keyframes rise{{0%{{opacity:0;transform:translate(0,0)}}20%{{opacity:1}}100%{{opacity:0;transform:translate(14px,-34px)}}}}
@keyframes twinkle{{0%,100%{{opacity:.15}}50%{{opacity:1}}}}
@keyframes caret{{0%,49%{{opacity:1}}50%,100%{{opacity:0}}}}
.eye{{transform-box:fill-box;transform-origin:center;animation:blink 5s infinite}}
.floaty{{animation:floaty 3.2s ease-in-out infinite}}
{extra}
@media (prefers-reduced-motion:reduce){{*{{animation:none!important}}}}
</style>"""


def svg(w: int, h: int, body: str, label: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
            f'role="img" aria-label="{escape(label)}">\n<title>{escape(label)}</title>\n{body}\n</svg>\n')


# ── data ────────────────────────────────────────────────────────────────────

TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")


def http(url: str, payload: dict | None = None):
    req = urllib.request.Request(url, data=json.dumps(payload).encode() if payload else None)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", f"{USER}-profile-cards")
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.load(r)


def kyiv_now() -> datetime:
    """Kyiv local time without tzdata: EET, EEST between the last Sundays of March and October."""
    utc = datetime.now(timezone.utc)

    def last_sunday(month: int) -> datetime:
        d = datetime(utc.year, month, 31, 1, tzinfo=timezone.utc)
        return d - timedelta(days=(d.weekday() + 1) % 7)

    offset = 3 if last_sunday(3) <= utc < last_sunday(10) else 2
    return utc.astimezone(timezone(timedelta(hours=offset)))


def fetch_calendar() -> dict[date, int]:
    if TOKEN:
        q = """query($login:String!){user(login:$login){contributionsCollection{contributionCalendar{
               weeks{contributionDays{date contributionCount}}}}}}"""
        try:
            res = http("https://api.github.com/graphql", {"query": q, "variables": {"login": USER}})
            weeks = res["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
            return {date.fromisoformat(d["date"]): d["contributionCount"] for w in weeks for d in w["contributionDays"]}
        except Exception as e:  # fall through to public events
            print("graphql calendar failed:", e)
    days: dict[date, int] = {}
    for page in (1, 2, 3):
        try:
            events = http(f"https://api.github.com/users/{USER}/events/public?per_page=100&page={page}")
        except Exception as e:
            print("events failed:", e)
            break
        for ev in events:
            p = ev.get("payload") or {}
            n = p.get("size") or len(p.get("commits") or []) or 1 if ev["type"] == "PushEvent" else 1
            day = datetime.fromisoformat(ev["created_at"].replace("Z", "+00:00")).astimezone(kyiv_now().tzinfo).date()
            days[day] = days.get(day, 0) + n
        if len(events) < 100:
            break
    return days


def fetch() -> dict:
    data = {"user": {}, "repos": {}, "langs": {}, "calendar": {}}
    try:
        user = http(f"https://api.github.com/users/{USER}")
        repos = http(f"https://api.github.com/users/{USER}/repos?per_page=100&type=owner")
        data["repos"] = {r["name"]: r for r in repos if not r["fork"]}
        for name in data["repos"]:
            for lang, size in http(f"https://api.github.com/repos/{USER}/{name}/languages").items():
                data["langs"][lang] = data["langs"].get(lang, 0) + size
        data["user"] = user  # set last, so a half-finished fetch counts as a failure
    except Exception as e:
        print("repo fetch failed:", e)
    data["calendar"] = fetch_calendar()
    return data


# ── pixel art ───────────────────────────────────────────────────────────────

CAT = [
    "..O.......O...",
    ".OIO.....OIO..",
    ".OIOOOOOOOIO..",
    ".OOOOOOOOOOO..",
    ".OOEOOOOOEOO..",
    ".OOEOOOOOEOO..",
    ".OCOOOPOOOCO..",
    "..OOOOOOOOO...",
    "..OOOOOOOOO...",
    ".OOOOOOOOOOO..",
    ".OOOOOOOOOOO..",
    ".OOOOOOOOOOO..",
    "..OO.....OO...",
]
# Two sprite frames for the tail swish; rotating pixel rects tears them apart.
CAT_TAIL = ([(12, 11), (13, 11), (13, 10), (13, 9), (13, 8)],
            [(12, 11), (13, 11), (13, 10), (14, 10), (14, 9)])


def cat(x: float, y: float, px: float, body: str, eye: str, mood: str = "chill") -> str:
    """Sitting pixel cat; (x, y) is the top-left corner."""
    colors = {"O": body, "I": "#ff9fb2", "C": "#ff9f9f", "P": "#ff7f9a"}
    rects, eyes = [], []
    for r, row in enumerate(CAT):
        for c, ch in enumerate(row):
            if ch == ".":
                continue
            if ch == "E":
                if mood == "sleepy" and r == 4:  # closed eyes: keep only the lower pixel
                    rects.append(f'<rect x="{x + c * px}" y="{y + r * px}" width="{px}" height="{px}" fill="{body}"/>')
                    continue
                eyes.append(f'<rect x="{x + c * px}" y="{y + r * px}" width="{px}" height="{px}" fill="{eye}"/>')
                continue
            op = ' opacity=".55"' if ch == "C" else ""
            rects.append(f'<rect x="{x + c * px}" y="{y + r * px}" width="{px}" height="{px}" fill="{colors[ch]}"{op}/>')
    tail = "".join(
        f'<g style="animation:caret 1.4s {-0.7 * i:.1f}s steps(1) infinite">'
        + "".join(f'<rect x="{x + c * px}" y="{y + r * px}" width="{px}" height="{px}" fill="{body}"/>' for c, r in frame)
        + "</g>" for i, frame in enumerate(CAT_TAIL))
    eye_cls = "" if mood == "sleepy" else ' class="eye"'
    return (f'<g shape-rendering="crispEdges">{tail}{"".join(rects)}'
            f'<g{eye_cls}>{"".join(eyes)}</g></g>')


ICONS = {
    "cat": ["a.......a", "aa.....aa", "aaaaaaaaa", "aabaaabaa", "aabaaabaa", "aaaacaaaa", ".aaaaaaa.", "..aaaaa..", "........."],
    "crosshair": ["....a....", "..bbabb..", ".b..a..b.", ".b.....b.", "aaa.c.aaa", ".b.....b.", ".b..a..b.", "..bbabb..", "....a...."],
    "parcel": ["..aaaaa..", ".abbcbba.", "abbbcbbba", "aaaacaaaa", "abbbcbbba", "abbbcbbba", "abbbbbbba", "abbbbbbba", "aaaaaaaaa"],
    "chat": [".aaaaaaa.", "abbbbbbba", "abbbbbbba", "abcbcbcba", "abbbbbbba", ".aaaaaaa.", "..aa.....", ".aa......", "........."],
    "sprout": [".......aa", ".....aaa.", "..bb.aa..", ".bbbba...", "..bbca...", "....c....", "....c....", "..ddddd..", "...ddd..."],
    "locked": ["...aaa...", "..a...a..", "..a...a..", ".bbbbbbb.", ".bbbcbbb.", ".bbbcbbb.", ".bbbbbbb.", ".bbbbbbb.", "........."],
}
ICON_COLORS = {
    "cat": ("peach", "text", "rose"), "crosshair": ("rose", "muted", "butter"),
    "parcel": ("butter", "peach", "text"), "chat": ("sky", "card", "text"),
    "sprout": ("mint", "mint", "muted", "peach"), "locked": ("muted", "border", "text"),
}


def icon(name: str, x: float, y: float, px: float, t: dict) -> str:
    pal = dict(zip("abcd", (t[k] for k in ICON_COLORS[name])))
    out = []
    for r, row in enumerate(ICONS[name]):
        for c, ch in enumerate(row):
            if ch != ".":
                out.append(f'<rect x="{x + c * px}" y="{y + r * px}" width="{px}" height="{px}" fill="{pal[ch]}"/>')
    return f'<g shape-rendering="crispEdges">{"".join(out)}</g>'


# ── hero: Kyiv right now ────────────────────────────────────────────────────

SKIES = {
    "dark": {"night": ("#08071a", "#2a1f4a"), "dawn": ("#2b2350", "#ff9e8a"), "day": ("#2f5f9e", "#9fcbf5"), "dusk": ("#24173f", "#ff8a7a")},
    "light": {"night": ("#2c2a5a", "#8a7fc0"), "dawn": ("#ffd6c9", "#fff1e0"), "day": ("#bfe3ff", "#f4fbff"), "dusk": ("#f7b9b0", "#ffe2c6")},
}


def sun_times(now: datetime) -> tuple[float, float]:
    """Approximate Kyiv sunrise and sunset in local hours (day length swings 8h–16h over the year)."""
    doy = now.timetuple().tm_yday
    length = 12.15 + 4.15 * math.sin(2 * math.pi * (doy - 80) / 365)
    noon = 11.95 + (now.utcoffset().total_seconds() / 3600 - 2)
    return noon - length / 2, noon + length / 2


def phase_of(hour: float, rise: float, sset: float) -> str:
    if rise - 0.7 <= hour < rise + 1:
        return "dawn"
    if rise + 1 <= hour < sset - 1:
        return "day"
    if sset - 1 <= hour < sset + 0.8:
        return "dusk"
    return "night"


def onion(cx: float, base: float, w: float, h: float) -> str:
    """Baroque pear dome sitting on `base`, w is the half-width of its drum."""
    return (f'M{cx - w:.1f},{base:.1f} C{cx - w * 1.45:.1f},{base - h * .4:.1f} {cx - w * .45:.1f},{base - h * .7:.1f} {cx:.1f},{base - h:.1f} '
            f'C{cx + w * .45:.1f},{base - h * .7:.1f} {cx + w * 1.45:.1f},{base - h * .4:.1f} {cx + w:.1f},{base:.1f}Z')


def cross(cx: float, top: float, s: float = 1) -> str:
    # the stem runs 6px past the bottom so it sinks into the pointed tip it stands on
    return (f'<rect x="{cx - .8 * s:.1f}" y="{top:.1f}" width="{1.6 * s:.1f}" height="{11 * s + 6:.1f}"/>'
            f'<rect x="{cx - 3.2 * s:.1f}" y="{top + 2.6 * s:.1f}" width="{6.4 * s:.1f}" height="{1.4 * s:.1f}"/>')


def landmarks(fill: str, gold: str, glow: str | None) -> str:
    """Right bank of the Dnipro: Lavra (Dormition Cathedral + Great Bell Tower), Motherland, TV tower."""
    out = []

    # Pechersk hills that carry the Lavra and the Motherland
    # starts at roof height where the left-bank blocks end, so there is no gap or cliff
    out.append(f'<path d="M530,340 V300 C580,298 640,296 730,296 S880,302 1000,312 V340Z" fill="{fill}"/>')

    def footing(x0: float, x1: float, b: float) -> None:
        """Solid ground from a landmark's base down to the frame, so nothing hangs over the hill."""
        out.append(f'<rect x="{x0}" y="{b - 1}" width="{x1 - x0}" height="{341 - b}" fill="{fill}"/>')

    # Dormition Cathedral: white baroque body, gables, seven golden domes
    cx, b = 598, 299
    footing(cx - 38, cx + 38, b)
    body = (f'M{cx - 36},{b} V{b - 30} L{cx - 30},{b - 36} H{cx - 14} Q{cx - 8},{b - 46} {cx},{b - 47} '
            f'Q{cx + 8},{b - 46} {cx + 14},{b - 36} H{cx + 30} L{cx + 36},{b - 30} V{b}Z')
    out.append(f'<path d="{body}" fill="{fill}"/>')
    domes = [(cx, b - 47, 7, 28, 16), (cx - 22, b - 36, 4.5, 18, 9), (cx + 22, b - 36, 4.5, 18, 9),
             (cx - 32, b - 33, 3, 12, 5), (cx + 32, b - 33, 3, 12, 5)]
    for dx, db, w, h, drum in domes:
        # drum runs down into the body: the curved gable under it is lower at the drum's edges
        out.append(f'<rect x="{dx - w}" y="{db - drum}" width="{2 * w}" height="{drum + 12}" fill="{fill}"/>')
        out.append(f'<path d="{onion(dx, db - drum, w, h)}" fill="{gold}"/>')
        out.append(f'<g fill="{gold}">{cross(dx, db - drum - h - 9, .8 if w < 5 else 1)}</g>')

    # Great Lavra Bell Tower: four classical tiers, gilded dome, spire
    cx, b = 672, 297
    footing(cx - 26, cx + 26, b)
    tiers = [(24, 40), (19, 30), (15, 24), (10, 18)]
    y = b
    for half, h in tiers:
        out.append(f'<rect x="{cx - half}" y="{y - h}" width="{2 * half}" height="{h}" fill="{fill}"/>')
        out.append(f'<rect x="{cx - half - 2}" y="{y - h - 3}" width="{2 * half + 4}" height="3" fill="{fill}"/>')
        if glow:  # arched openings, lit at night
            for k in (-1, 0, 1) if half > 12 else (0,):
                ax = cx + k * half * .55
                out.append(f'<path d="M{ax - 2.4:.1f},{y - 4} v{-(h - 14)} a2.4,2.4 0 0 1 4.8,0 v{h - 14}z" fill="{glow}" opacity=".75"/>')
        y -= h + 3
    # lantern, spire and cross each start inside the shape below and are drawn behind it,
    # so they never rest on a single point of a curve
    out.append(f'<rect x="{cx - 2.5}" y="{y - 29}" width="5" height="14" fill="{fill}"/>')
    out.append(f'<path d="M{cx - 11},{y} C{cx - 11},{y - 15} {cx - 5},{y - 19} {cx},{y - 19} '
               f'C{cx + 5},{y - 19} {cx + 11},{y - 15} {cx + 11},{y}Z" fill="{gold}"/>')
    out.append(f'<path d="M{cx - 1.2},{y - 33} L{cx - .5},{y - 56} H{cx + .5} L{cx + 1.2},{y - 33}Z" fill="{gold}"/>'
               f'<path d="{onion(cx, y - 29, 3, 8)}" fill="{gold}"/>')
    out.append(f'<g fill="{gold}">{cross(cx, y - 63, .9)}</g>')

    # Motherland Monument on its museum base: robe, raised sword, shield at her side
    cx, b = 790, 297
    footing(cx - 34, cx + 34, b)
    m = [
        f'M{cx - 34},{b} L{cx - 30},{b - 14} H{cx + 30} L{cx + 34},{b}Z',               # museum
        f'M{cx - 22},{b - 14} V{b - 22} H{cx + 22} V{b - 14}Z',                          # terrace
        f'M{cx - 9},{b - 22} L{cx - 7},{b - 44} H{cx + 7} L{cx + 9},{b - 22}Z',           # pedestal
        f'M{cx - 10},{b - 44} C{cx - 8},{b - 62} {cx - 6},{b - 74} {cx - 5},{b - 86} '    # robe and torso
        f'L{cx - 7},{b - 96} Q{cx},{b - 99} {cx + 7},{b - 97} L{cx + 5},{b - 86} '
        f'C{cx + 6},{b - 74} {cx + 8},{b - 62} {cx + 11},{b - 44}Z',
        f'M{cx},{b - 98} Q{cx + 9},{b - 104} {cx + 12},{b - 118} L{cx + 17},{b - 116} Q{cx + 13},{b - 100} {cx + 4},{b - 88}Z',  # raised right arm
        f'M{cx - 6},{b - 95} L{cx - 12},{b - 82} L{cx - 9},{b - 80} L{cx - 3},{b - 92}Z',      # left arm to shield
    ]
    # one element per part: overlapping subpaths of opposite winding would cut holes
    out.extend(f'<path d="{part}" fill="{fill}"/>' for part in m)
    out.append(f'<circle cx="{cx}" cy="{b - 103}" r="4.2" fill="{fill}"/>')
    out.append(f'<ellipse cx="{cx - 14}" cy="{b - 78}" rx="6.5" ry="9.5" transform="rotate(-12 {cx - 14} {b - 78})" fill="{fill}"/>')
    # sword: guard at the fist, blade pointing up and slightly outward
    sx, sy = cx + 14.5, b - 117
    out.append(f'<circle cx="{sx}" cy="{sy}" r="3" fill="{fill}"/>')
    out.append(f'<path d="M{sx - 4},{sy + 1} L{sx + 4},{sy - 1} L{sx + 4},{sy + 1} L{sx - 4},{sy + 3}Z '
               f'M{sx - 1.2},{sy} L{sx + 2.6},{sy - 46} L{sx + 3.6},{sy - 50} L{sx + 3.8},{sy - 45} L{sx + 1.2},{sy}Z" fill="{fill}"/>')

    # Kyiv TV Tower: splayed lattice tripod, shaft, two platforms, antenna mast
    cx, b = 908, 308
    lattice = "".join(f'<path d="M{cx - 15 + k * 2.2:.1f},{b - k * 9} L{cx + 15 - (k + 1) * 2.2:.1f},{b - (k + 1) * 9}" />'
                      f'<path d="M{cx + 15 - k * 2.2:.1f},{b - k * 9} L{cx - 15 + (k + 1) * 2.2:.1f},{b - (k + 1) * 9}" />'
                      for k in range(6))
    out.append(f'<path d="M{cx - 16},{b} L{cx - 2.5},{b - 62} H{cx + 2.5} L{cx + 16},{b} H{cx + 12} L{cx + 1},{b - 50} H{cx - 1} L{cx - 12},{b}Z" fill="{fill}"/>'
               f'<g stroke="{fill}" stroke-width="1.2" fill="none">{lattice}</g>'
               f'<path d="M{cx - 2.5},{b - 62} L{cx - 1.8},{b - 150} H{cx + 1.8} L{cx + 2.5},{b - 62}Z" fill="{fill}"/>'
               f'<rect x="{cx - 9}" y="{b - 132}" width="18" height="6" rx="1.5" fill="{fill}"/>'
               f'<rect x="{cx - 6}" y="{b - 118}" width="12" height="4" rx="1" fill="{fill}"/>'
               f'<rect x="{cx - .9}" y="{b - 196}" width="1.8" height="48" fill="{fill}"/>')
    out.append(f'<circle cx="{cx}" cy="{b - 198}" r="2.6" fill="#ff4d4d" style="animation:twinkle 1.6s infinite"/>'
               f'<circle cx="{cx}" cy="{b - 131}" r="1.6" fill="#ff4d4d" style="animation:twinkle 1.6s .8s infinite"/>')
    return "".join(out)


def skyline(fill: str, lit: bool, t: dict) -> str:
    rnd = random.Random(24)
    parts, windows = [], []
    x = 0
    while x < 548:  # the left bank; the right bank is hills and landmarks
        w = min(rnd.randint(34, 70), 548 - x)
        top = 340 - rnd.randint(36, 86)
        if 450 <= x <= 520:
            top = 272  # the cat's roof
        parts.append(f'<rect x="{x}" y="{top}" width="{w + 1}" height="{340 - top}"/>')
        if lit:
            for wy in range(top + 10, 330, 14):
                for wx in range(x + 7, x + w - 8, 12):
                    if rnd.random() < 0.22:
                        d = rnd.uniform(0, 9)
                        windows.append(f'<rect x="{wx}" y="{wy}" width="5" height="6" rx="1" fill="#ffd98a" '
                                       f'style="animation:twinkle {rnd.uniform(4, 11):.1f}s {d:.1f}s infinite"/>')
        x += w
    gold = "#e9b949" if not lit else "#c99a3c"
    return (f'<g fill="{fill}">{"".join(parts)}</g>{"".join(windows)}'
            f'{landmarks(fill, gold, "#ffd98a" if lit else None)}')


def typewriter(roles: list[str], x: float, y: float, t: dict, color: str) -> str:
    cw, slot = 12.0, 4.0
    n = len(roles)
    dur = n * slot
    timeline: list[tuple[float, float]] = []
    texts = []
    for i, role in enumerate(roles):
        s, L = i / n, len(role)
        frames = [(s, 0.0)]
        frames += [(s + 0.45 * k / L / n, k * cw) for k in range(1, L + 1)]
        frames += [(s + (0.8 + 0.15 * (L - k) / L) / n, k * cw) for k in range(L - 1, -1, -1)]
        timeline += frames
        e = (i + 1) / n
        if i == 0:
            vis_v, vis_t = "1;0", f"0;{e:.4f}"
        elif i == n - 1:
            vis_v, vis_t = "0;1", f"0;{s:.4f}"
        else:
            vis_v, vis_t = "0;1;0", f"0;{s:.4f};{e:.4f}"
        texts.append(f'<text x="{x}" y="{y}" class="mono" font-size="20" fill="{color}" textLength="{L * cw}" '
                     f'lengthAdjust="spacingAndGlyphs" opacity="0"><animate attributeName="opacity" calcMode="discrete" '
                     f'values="{vis_v}" keyTimes="{vis_t}" dur="{dur}s" repeatCount="indefinite"/>{escape(role)}</text>')
    clean: list[tuple[float, float]] = []
    for tt, w in timeline:
        if not clean or tt > clean[-1][0] + 1e-4:
            clean.append((tt, w))
    kt = ";".join(f"{a:.4f}" for a, _ in clean)
    widths = ";".join(f"{w:.0f}" for _, w in clean)
    xs = ";".join(f"{x + w + 2:.0f}" for _, w in clean)
    return (f'<clipPath id="tw"><rect x="{x}" y="{y - 22}" height="30" width="0">'
            f'<animate attributeName="width" calcMode="discrete" values="{widths}" keyTimes="{kt}" dur="{dur}s" repeatCount="indefinite"/>'
            f'</rect></clipPath><g clip-path="url(#tw)">{"".join(texts)}</g>'
            f'<rect y="{y - 18}" width="10" height="22" fill="{color}" style="animation:caret 1s steps(1) infinite">'
            f'<animate attributeName="x" calcMode="discrete" values="{xs}" keyTimes="{kt}" dur="{dur}s" repeatCount="indefinite"/></rect>')


def hero(t: dict, theme: str, now: datetime) -> str:
    hour = now.hour + now.minute / 60
    rise, sset = sun_times(now)
    ph = phase_of(hour, rise, sset)
    top, bot = SKIES[theme][ph]
    on_dark = theme == "dark" or ph == "night"
    ink = "#fff7ee" if on_dark else "#1d1a24"
    soft = "#fff7ee" if on_dark else "#4a4358"
    city = {"dark": "#0a0912", "light": "#1c1838" if ph == "night" else "#5a5076"}[theme]
    rnd = random.Random(now.strftime("%Y%m%d"))
    sky = []

    if ph in ("night", "dusk", "dawn"):
        count = {"night": 90, "dusk": 40, "dawn": 18}[ph]
        for _ in range(count):
            sx, sy, r = rnd.uniform(10, 990), rnd.uniform(10, 250), rnd.choice((0.7, 0.9, 1.1, 1.5))
            sky.append(f'<circle cx="{sx:.0f}" cy="{sy:.0f}" r="{r}" fill="#fff" '
                       f'style="animation:twinkle {rnd.uniform(2, 6):.1f}s {rnd.uniform(0, 5):.1f}s infinite"/>')
    if ph == "night":
        sky.append('<g style="animation:shoot 9s 2s infinite"><line x1="0" y1="0" x2="90" y2="0" stroke="url(#trail)" stroke-width="2" stroke-linecap="round"/></g>')
    if ph in ("day", "dawn"):
        for i in range(5):
            cx, cy, s = rnd.uniform(80, 900), rnd.uniform(40, 170), rnd.uniform(0.7, 1.3)
            sky.append(f'<g opacity=".8" style="animation:drift {rnd.uniform(40, 70):.0f}s {-rnd.uniform(0, 60):.0f}s linear infinite">'
                       f'<g transform="translate({cx:.0f} {cy:.0f}) scale({s:.2f})" fill="#fff">'
                       f'<ellipse cx="0" cy="0" rx="34" ry="12"/><ellipse cx="-14" cy="-8" rx="16" ry="12"/><ellipse cx="12" cy="-10" rx="18" ry="14"/></g></g>')

    sun = rise <= hour < sset
    span = (hour - rise) / (sset - rise) if sun else ((hour - sset) % 24) / (24 - (sset - rise))
    bx, by = 600 + span * 340, 262 - math.sin(math.pi * span) * 190
    if sun:
        body = (f'<circle cx="{bx:.0f}" cy="{by:.0f}" r="46" fill="#ffd27a" opacity=".25" style="animation:twinkle 5s infinite"/>'
                f'<circle cx="{bx:.0f}" cy="{by:.0f}" r="26" fill="#ffd27a"/>')
    else:
        body = (f'<circle cx="{bx:.0f}" cy="{by:.0f}" r="40" fill="#fff4d6" opacity=".12"/>'
                f'<mask id="moon"><rect width="1000" height="340" fill="#fff"/><circle cx="{bx + 11:.0f}" cy="{by - 7:.0f}" r="20" fill="#000"/></mask>'
                f'<circle cx="{bx:.0f}" cy="{by:.0f}" r="22" fill="#fff4d6" mask="url(#moon)"/>')

    label = {"night": "night", "dawn": "dawn", "day": "day", "dusk": "golden hour"}[ph]
    glyph = {"night": "☾", "dawn": "◐", "day": "☀", "dusk": "◑"}[ph]
    utc_off = int(now.utcoffset().total_seconds() // 3600)
    extra = ("@keyframes shoot{0%{transform:translate(120px,30px) rotate(18deg);opacity:0}2%{opacity:1}"
             "9%{transform:translate(520px,160px) rotate(18deg);opacity:0}100%{opacity:0}}"
             "@keyframes drift{from{transform:translateX(-120px)}to{transform:translateX(1120px)}}"
             "@keyframes rise2{0%{opacity:0;transform:translateY(8px)}100%{opacity:1;transform:none}}"
             ".in{animation:rise2 .9s ease-out both}")
    body_svg = f"""{base_css(t, extra)}
<defs>
<linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{top}"/><stop offset="1" stop-color="{bot}"/></linearGradient>
<linearGradient id="trail"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset="1" stop-color="#fff"/></linearGradient>
<linearGradient id="ua" x1="0" x2="1"><stop offset="0" stop-color="#3d8bff"/><stop offset="1" stop-color="#ffd34d"/></linearGradient>
<clipPath id="frame"><rect width="1000" height="340" rx="22"/></clipPath>
</defs>
<g clip-path="url(#frame)">
<rect width="1000" height="340" fill="url(#sky)"/>
{''.join(sky)}
{body}
{skyline(city, ph in ("night", "dusk"), t)}
<g transform="translate(470 220)">{cat(0, 0, 4, "#f3d9c4", "#1b1626", "sleepy" if ph == "night" and hour < 5 else "chill")}</g>
<rect y="336" width="1000" height="4" fill="url(#ua)"/>
</g>
<g class="in">
<text x="48" y="64" class="mono" font-size="15" fill="{soft}" opacity=".85">{USER}@kyiv:~$ whoami</text>
<text x="46" y="124" class="sans" font-size="54" font-weight="800" fill="{ink}" letter-spacing="-1">{escape(NAME)}</text>
<text x="48" y="168" class="mono" font-size="20" fill="{t['peach'] if theme == 'dark' else ('#ffb4a2' if on_dark else '#c4553c')}">&gt;</text>
{typewriter(ROLES, 70, 168, t, ink)}
<text x="48" y="206" class="mono" font-size="14" fill="{soft}" opacity=".8">Kyiv, UA · {now:%H:%M} UTC+{utc_off} · {glyph} {label} over the Dnipro</text>
</g>"""
    return svg(1000, 340, body_svg, f"{NAME}, {ROLES[0]} from Kyiv. The sky shows Kyiv at {now:%H:%M}.")


# ── neko.status: activity as a tamagotchi ───────────────────────────────────

MOODS = {
    "sleepy": ("asleep", "Quiet week. The cat is napping on the keyboard."),
    "chill": ("chill", "A few commits in. The cat approves, mildly."),
    "happy": ("happy", "Shipping steadily. The cat is purring."),
    "hyped": ("hyped", "On a roll this week. The cat cannot sit still."),
}


def streak(cal: dict[date, int], today: date) -> int:
    d = today if cal.get(today, 0) else today - timedelta(days=1)
    n = 0
    while cal.get(d, 0) > 0:
        n += 1
        d -= timedelta(days=1)
    return n


def smooth(pts: list[tuple[float, float]], floor: float) -> str:
    d = f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"
    for i in range(len(pts) - 1):
        p0, p1, p2 = pts[max(i - 1, 0)], pts[i], pts[i + 1]
        p3 = pts[min(i + 2, len(pts) - 1)]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, min(floor, p1[1] + (p2[1] - p0[1]) / 6))
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, min(floor, p2[1] - (p3[1] - p1[1]) / 6))
        d += f" C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {p2[0]:.1f},{p2[1]:.1f}"
    return d


def neko(t: dict, data: dict, now: datetime) -> str:
    cal, today = data["calendar"], now.date()
    week = sum(cal.get(today - timedelta(days=i), 0) for i in range(7))
    year = sum(v for d, v in cal.items() if d.year == today.year)
    mood = "sleepy" if week == 0 else "chill" if week < 5 else "happy" if week < 15 else "hyped"
    mood_label, line = MOODS[mood]

    fx = []
    if mood == "sleepy":
        fx = [f'<text x="{150 + i * 8}" y="{70 - i * 4}" class="mono" font-size="{14 + i * 3}" fill="{t["lav"]}" '
              f'style="animation:rise 3.6s {i * 1.2}s infinite">z</text>' for i in range(3)]
    elif mood == "happy":
        fx = [f'<text x="{140 + i * 14}" y="76" font-size="16" fill="{t["rose"]}" style="animation:rise 3s {i}s infinite">♥</text>' for i in range(3)]
    elif mood == "hyped":
        fx = [f'<text x="{60 + i * 46}" y="{60 + (i % 2) * 18}" font-size="18" fill="{t["butter"]}" '
              f'style="animation:twinkle 1.{3 + i}s {i * .3:.1f}s infinite">✦</text>' for i in range(4)]
    else:
        fx = [f'<text x="{148 + i * 12}" y="74" font-size="16" fill="{t["mint"]}" style="animation:rise 3.4s {i * 1.1:.1f}s infinite">♪</text>' for i in range(2)]
    bounce = ' style="animation:floaty .7s ease-in-out infinite"' if mood == "hyped" else ""

    tiles = [("this week", f"{week}", "contributions"), ("streak", f"{streak(cal, today)}", "days in a row"),
             (str(today.year), f"{year}", "contributions"), ("repos", f"{data['user'].get('public_repos', len(data['repos']))}", "public")]
    tile_svg = []
    for i, (k, v, sub) in enumerate(tiles):
        tx = 290 + i * 172
        tile_svg.append(f'<g class="pop" style="animation-delay:{i * .12:.2f}s"><rect x="{tx}" y="64" width="158" height="74" rx="14" fill="{t["bg"]}" stroke="{t["border"]}"/>'
                        f'<text x="{tx + 16}" y="88" class="mono mu" font-size="12">{escape(k)}</text>'
                        f'<text x="{tx + 16}" y="122" class="sans fg" font-size="28" font-weight="700">{v}</text>'
                        f'<text x="{tx + 142}" y="122" class="sans mu" font-size="12" text-anchor="end">{sub}</text></g>')

    days = [today - timedelta(days=29 - i) for i in range(30)]
    vals = [cal.get(d, 0) for d in days]
    peak = max(vals + [1])
    x0, x1, y0, y1 = 300, 966, 168, 228
    pts = [(x0 + i * (x1 - x0) / 29, y1 - v / peak * (y1 - y0)) for i, v in enumerate(vals)]
    path = smooth(pts, y1)
    accent = {"sleepy": t["lav"], "chill": t["mint"], "happy": t["rose"], "hyped": t["butter"]}[mood]

    extra = ("@keyframes draw{0%{stroke-dashoffset:1}45%,100%{stroke-dashoffset:0}}"
             "@keyframes pop{0%{opacity:0;transform:translateY(6px)}100%{opacity:1;transform:none}}"
             ".pop{animation:pop .6s ease-out both}.line{stroke-dasharray:1;animation:draw 6s ease-out infinite}")
    body = f"""{base_css(t, extra)}
<defs><linearGradient id="area" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{accent}" stop-opacity=".35"/><stop offset="1" stop-color="{accent}" stop-opacity="0"/></linearGradient></defs>
<rect x=".5" y=".5" width="999" height="259" rx="22" fill="{t['card']}" stroke="{t['border']}"/>
<text x="32" y="40" class="mono mu" font-size="13">~/neko.status</text>
<g transform="translate(64 84)"><g{bounce}>{cat(0, 0, 8, t['cat'], t['cat_eye'], mood)}</g></g>
{''.join(fx)}
<rect x="62" y="206" width="124" height="28" rx="14" fill="{accent}" opacity=".18"/>
<text x="124" y="225" class="mono" font-size="13" fill="{accent}" text-anchor="middle">mood: {mood_label}</text>
<text x="290" y="44" class="sans fg" font-size="17" font-weight="600">{escape(line)}</text>
{''.join(tile_svg)}
<path d="{path} L{x1},{y1} L{x0},{y1} Z" fill="url(#area)"/>
<path id="pulse" d="{path}" fill="none" stroke="{accent}" stroke-width="2.5" stroke-linecap="round" pathLength="1" class="line"/>
<circle r="4.5" fill="{accent}"><animateMotion dur="6s" repeatCount="indefinite" keyPoints="0;1;1" keyTimes="0;.45;1" calcMode="linear"><mpath href="#pulse"/></animateMotion></circle>
<text x="{x0}" y="246" class="mono mu" font-size="11">30 days ago</text>
<text x="{x1}" y="246" class="mono mu" font-size="11" text-anchor="end">today · peak {peak}/day</text>"""
    return svg(1000, 260, body, f"Activity: {week} contributions this week, {year} in {today.year}. Mood: {mood_label}.")


# ── inventory: projects as RPG items ────────────────────────────────────────

RARITY = [(6, "legendary", "butter"), (4, "epic", "lav"), (2, "rare", "sky"), (0, "common", "muted")]


def ago(iso: str | None, now: datetime) -> str:
    if not iso:
        return "—"
    days = (now - datetime.fromisoformat(iso.replace("Z", "+00:00"))).days
    return "today" if days < 1 else f"{days}d ago" if days < 60 else f"{days // 30}mo ago"


def wrap(text: str, width: int) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        if len(cur) + len(word) + 1 > width:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}".strip()
    return lines + [cur]


def item_card(t: dict, repo: dict | None, name: str, blurb: str, ico: str, now: datetime) -> str:
    stars = (repo or {}).get("stargazers_count", 0)
    pushed = (repo or {}).get("pushed_at")
    age = (now - datetime.fromisoformat(pushed.replace("Z", "+00:00"))).days if pushed else 999
    score = stars * 2 + (3 if age <= 14 else 2 if age <= 60 else 1 if age <= 180 else 0)
    _, rarity, rkey = next(r for r in RARITY if score >= r[0])
    rc = t[rkey]
    lang = (repo or {}).get("language") or "—"
    shimmer = rarity in ("legendary", "epic")
    stroke = "url(#shine)" if shimmer else (rc if rarity == "rare" else t["border"])
    lines = wrap(blurb, 44)[:3]
    blurb_svg = "".join(f'<text x="132" y="{94 + i * 19}" class="sans mu" font-size="14">{escape(l)}</text>' for i, l in enumerate(lines))
    body = f"""{base_css(t)}
<defs><linearGradient id="shine" x1="0" y1="0" x2="1" y2="0" gradientUnits="objectBoundingBox">
<stop offset="0" stop-color="{rc}" stop-opacity=".25"/><stop offset=".5" stop-color="{rc}"/><stop offset="1" stop-color="{rc}" stop-opacity=".25"/>
<animateTransform attributeName="gradientTransform" type="translate" values="-1 0;1 0" dur="3.5s" repeatCount="indefinite"/></linearGradient></defs>
<rect x="6" y="6" width="488" height="168" rx="18" fill="{t['card']}" stroke="{stroke}" stroke-width="{2 if rarity != 'common' else 1}"/>
<rect x="24" y="30" width="88" height="88" rx="14" fill="{t['bg']}" stroke="{t['border']}"/>
<rect x="24" y="30" width="88" height="88" rx="14" fill="{rc}" opacity=".08"/>
<g class="floaty">{icon(ico, 41, 47, 6, t)}</g>
<text x="68" y="146" class="mono" font-size="11" fill="{rc}" text-anchor="middle" letter-spacing="1.5">{rarity.upper()}</text>
<text x="132" y="62" class="sans fg" font-size="21" font-weight="700">{escape(name)}</text>
{blurb_svg}
<circle cx="138" cy="152" r="5" fill="{LANG_COLORS.get(lang, t['muted'])}"/>
<text x="150" y="156" class="mono mu" font-size="12">{escape(lang)}   ★ {stars}   ↻ {ago(pushed, now)}</text>"""
    return svg(500, 180, body, f"{name}: {blurb}")


def locked_card(t: dict) -> str:
    dots = "".join(f'<tspan style="animation:caret 1.5s {i * .5:.1f}s infinite">.</tspan>' for i in range(3))
    body = f"""{base_css(t)}
<rect x="6" y="6" width="488" height="168" rx="18" fill="none" stroke="{t['border']}" stroke-width="1.5" stroke-dasharray="7 7">
<animate attributeName="stroke-dashoffset" values="0;28" dur="2s" repeatCount="indefinite"/></rect>
<rect x="24" y="30" width="88" height="88" rx="14" fill="{t['bg']}" stroke="{t['border']}"/>
<g class="floaty" opacity=".8">{icon('locked', 41, 47, 6, t)}</g>
<text x="68" y="146" class="mono mu" font-size="11" text-anchor="middle" letter-spacing="1.5">LOCKED</text>
<text x="132" y="62" class="sans fg" font-size="21" font-weight="700">next quest loading{dots}</text>
<text x="132" y="94" class="sans mu" font-size="14">Something new is in the forge.</text>
<text x="132" y="113" class="sans mu" font-size="14">Follow along to unlock it first.</text>"""
    return svg(500, 180, body, "Locked slot: next project in progress")


# ── stack as a Kyiv metro map ───────────────────────────────────────────────

def metro(t: dict, data: dict) -> str:
    total = sum(data["langs"].values()) or 1
    share = {k: v / total for k, v in data["langs"].items()}
    hub = (96, 236)
    rows = [116, 196, 276, 352]
    lines_svg, trains, stations = [], [], []
    for i, ((code, title, color, items, building), y) in enumerate(zip(METRO, rows)):
        c = t[color]
        dy = abs(y - hub[1])
        sx = hub[0] + max(dy, 60)
        end = 950 if not building else 690
        d = f"M{hub[0]},{hub[1]} L{sx},{y} L{end},{y}"
        dash = ' stroke-dasharray="14 10" class="build"' if building else ""
        lines_svg.append(f'<path id="l{i}" d="{d}" fill="none" stroke="{c}" stroke-width="8" stroke-linecap="round" stroke-linejoin="round"{dash}/>')
        trains.append(f'<g><rect x="-13" y="-5" width="26" height="10" rx="5" fill="{c}" stroke="{t["card"]}" stroke-width="2"/>'
                      f'<rect x="-7" y="-2" width="4" height="4" fill="{t["card"]}"/><rect x="3" y="-2" width="4" height="4" fill="{t["card"]}"/>'
                      f'<animateMotion dur="{9 + i * 1.5}s" begin="{i * 1.3}s" repeatCount="indefinite" rotate="auto"><mpath href="#l{i}"/></animateMotion>'
                      f'<animate attributeName="opacity" values="0;1;1;0" keyTimes="0;.06;.92;1" dur="{9 + i * 1.5}s" begin="{i * 1.3}s" repeatCount="indefinite"/></g>')
        badge_w = 34 + len(title) * 7.4
        x_start = sx + 14 + badge_w + 54
        step = (end - 30 - x_start) / max(len(items) - 1, 1)
        for j, item in enumerate(items):
            x = x_start + j * step
            stations.append(f'<circle cx="{x:.0f}" cy="{y}" r="7" fill="{t["station"]}" stroke="{c}" stroke-width="3.5"/>'
                            f'<text x="{x:.0f}" y="{y - 16}" class="sans fg" font-size="13" font-weight="600" text-anchor="middle">{escape(item)}</text>')
            if item in share and share[item] >= 0.005:
                stations.append(f'<text x="{x:.0f}" y="{y + 25}" class="mono mu" font-size="11" text-anchor="middle">{share[item] * 100:.0f}% of code</text>')
        stations.append(f'<rect x="{sx + 14}" y="{y - 30}" width="{badge_w:.0f}" height="20" rx="10" fill="{c}"/>'
                        f'<text x="{sx + 24}" y="{y - 16}" class="mono" font-size="11" font-weight="700" fill="{t["card"]}">{code} {escape(title)}</text>')
        if building:
            stations.append(f'<g transform="translate({end + 18} {y - 12})"><rect width="44" height="24" rx="3" fill="{c}"/>'
                            + "".join(f'<path d="M{k * 12 - 4},24 L{k * 12 + 6},0 L{k * 12 + 12},0 L{k * 12 + 2},24z" fill="#1d1a24"/>' for k in range(4))
                            + f'</g><text x="{end + 76}" y="{y - 2}" class="mono mu" font-size="12">under construction</text>'
                            f'<text x="{end + 76}" y="{y + 14}" class="mono mu" font-size="12">next station: ?</text>')

    river = (f'<path d="M560 0 C600 80 520 150 580 220 S640 330 600 420 L700 420 C740 330 680 250 700 200 S640 60 680 0 Z" fill="{t["river"]}" opacity=".9"/>'
             f'<text x="0" y="0" class="mono" font-size="11" fill="{t["sky"]}" opacity=".8" letter-spacing="3" '
             f'transform="translate(668 300) rotate(-72)">DNIPRO</text>')
    hub_svg = (f'<circle cx="{hub[0]}" cy="{hub[1]}" r="20" fill="{t["station"]}" stroke="{t["text"]}" stroke-width="4"/>'
               f'<circle cx="{hub[0]}" cy="{hub[1]}" r="7" fill="{t["text"]}"><animate attributeName="r" values="6;9;6" dur="2.4s" repeatCount="indefinite"/></circle>'
               f'<text x="{hub[0]}" y="{hub[1] + 42}" class="mono fg" font-size="12" font-weight="700" text-anchor="middle">{USER}</text>')
    extra = "@keyframes build{to{stroke-dashoffset:-48}}.build{animation:build 1.6s linear infinite}"
    body = f"""{base_css(t, extra)}
<defs><clipPath id="m"><rect width="1000" height="420" rx="22"/></clipPath></defs>
<g clip-path="url(#m)"><rect width="1000" height="420" fill="{t['card']}"/>{river}</g>
<rect x=".5" y=".5" width="999" height="419" rx="22" fill="none" stroke="{t['border']}"/>
<text x="32" y="46" class="sans fg" font-size="22" font-weight="800">Stack</text>
<text x="104" y="46" class="mono mu" font-size="13">as a Kyiv metro map · share of code is live from my repos</text>
{''.join(lines_svg)}{''.join(trains)}{hub_svg}{''.join(stations)}"""
    return svg(1000, 420, body, "Tech stack drawn as a Kyiv metro map: " + "; ".join(f"{m[1]}: {', '.join(m[3])}" for m in METRO))


# ── footer ──────────────────────────────────────────────────────────────────

def footer(t: dict, now: datetime) -> str:
    extra = ("@keyframes walk{from{transform:translateX(-90px)}to{transform:translateX(1010px)}}"
             "@keyframes step{0%,100%{transform:translateY(0)}50%{transform:translateY(-3px)}}"
             ".walk{animation:walk 22s linear infinite}.step{animation:step .45s steps(2) infinite}")
    body = f"""{base_css(t, extra)}
<defs><linearGradient id="ua2" x1="0" x2="1"><stop offset="0" stop-color="#3d8bff"/><stop offset="1" stop-color="#ffd34d"/></linearGradient></defs>
<text x="500" y="44" class="sans fg" font-size="20" font-weight="700" text-anchor="middle">Thanks for riding along.</text>
<text x="500" y="70" class="mono mu" font-size="12" text-anchor="middle">This page rebuilds itself every 2 hours · last train left {now:%d %b, %H:%M} Kyiv time</text>
<g class="walk"><g class="step">{cat(0, 98, 3, t['cat'], t['cat_eye'])}</g></g>
<rect x="0" y="138" width="1000" height="3" rx="1.5" fill="url(#ua2)" opacity=".85"/>"""
    return svg(1000, 150, body, "Thanks for visiting. A pixel cat walks across the page.")


# ── main ────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="dist")
    out = Path(ap.parse_args().out)
    out.mkdir(parents=True, exist_ok=True)

    now = kyiv_now()
    if os.environ.get("HERO_HOUR"):  # preview a different time of day
        now = now.replace(hour=int(os.environ["HERO_HOUR"]), minute=0)
    data = fetch()
    if not data["user"]:
        # Keep the last good cards on the output branch rather than publishing zeros.
        raise SystemExit("GitHub API unavailable, not writing cards")

    for theme, t in THEMES.items():
        cards = {
            "hero": hero(t, theme, now),
            "neko": neko(t, data, now),
            "metro": metro(t, data),
            "footer": footer(t, now),
            "item-locked": locked_card(t),
        }
        for repo, blurb, ico in PROJECTS:
            cards[f"item-{repo}"] = item_card(t, data["repos"].get(repo), repo, blurb, ico, now)
        for name, content in cards.items():
            (out / f"{name}-{theme}.svg").write_text(content, encoding="utf-8")
    print(f"wrote {len(list(out.glob('*.svg')))} cards to {out}")


if __name__ == "__main__":
    main()
