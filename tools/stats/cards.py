#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["jinja2==3.1.6"]
# ///
"""Render the follow-up card (issues and pull requests) to metrics/status-*.svg.

Reads .cache/prs.json and .cache/issues.json written by fetch.sh and fills the
Jinja template card.svg.j2. Run with `uv run --script tools/stats/cards.py`.
"""

import base64
import collections
import datetime
import json
import pathlib

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
ME = "laraibg786"
TEAM_ROLES = ("MEMBER", "OWNER", "COLLABORATOR")

WIDTH, COL_WIDTH = 640, 280
GROUP_HEIGHT = 40 + 22 * 2 + 20  # same in every column so the groups line up
GREEN, PURPLE, RED = "#3fb950", "#a371f7", "#f85149"
COLORS = {"open": GREEN, "closed": PURPLE, "merged": PURPLE, "rej": RED}
THEMES = {
    "light": "--bg:#fff;--bd:#d0d7de;--fg:#1f2328;--mu:#59636e;--ac:#0969da",
    "dark": "--bg:#0d1117;--bd:#30363d;--fg:#e6edf3;--mu:#8b949e;--ac:#2f81f7",
}
GROUPS = (("From communities", "outside"), ("From self and collaborators", "team"))
# column name, source file, then (state, icon kind) per row
COLUMNS = (
    ("Issues", "issues.json", (("open", "open"), ("closed", "closed"))),
    (
        "Pull requests",
        "prs.json",
        (("open", "open"), ("merged", "merged"), ("closed", "rej")),
    ),
)


def font(weight: str) -> str:
    return base64.b64encode(
        (ROOT / f"assets/fonts/jbm-{weight}.woff2").read_bytes()
    ).decode()


def tally(name: str) -> dict[str, collections.Counter]:
    rows = json.loads((ROOT / ".cache" / name).read_text())
    counts: dict[str, collections.Counter] = collections.defaultdict(
        collections.Counter
    )
    for row in rows:
        author = row["author"] or {}
        if author.get("__typename") == "Bot":
            continue
        team = author.get("login") == ME or row["authorAssociation"] in TEAM_ROLES
        counts["team" if team else "outside"][row["state"]] += 1
    return counts


def segments(x: float, counts: collections.Counter, is_issue: bool) -> list[dict]:
    parts = [
        (counts["open"], GREEN),
        (counts["merged"], PURPLE),
        (counts["closed"], PURPLE if is_issue else RED),
    ]
    total = sum(n for n, _ in parts) or 1
    out = []
    for n, color in parts:
        if n:
            width = COL_WIDTH * n / total
            out.append({"x": round(x, 1), "w": round(width, 1), "color": color})
            x += width
    return out


def build_context() -> dict:
    columns = []
    for index, (name, source, items) in enumerate(COLUMNS):
        counts = tally(source)
        x = 20 + index * (WIDTH / 2)
        groups = []
        for g_index, (g_name, key) in enumerate(GROUPS):
            y = 100 + g_index * GROUP_HEIGHT
            c = counts[key]
            rows = []
            for n, (state, icon) in enumerate(items):
                ix, iy = x + (n % 2) * 140, y + 40 + (n // 2) * 22
                rows.append(
                    {
                        "icon": icon,
                        "x": ix,
                        "y": iy,
                        "count": c[state],
                        "label": state,
                        "label_x": ix + 18 + 7 * len(str(c[state])) + 5,
                    }
                )
            groups.append(
                {
                    "id": f"bar{index}{g_index}",
                    "name": g_name,
                    "y": y,
                    "segments": segments(x, c, name == "Issues"),
                    "rows": rows,
                }
            )
        columns.append({"name": name, "x": x, "groups": groups})
    footer_y = 100 + len(GROUPS) * GROUP_HEIGHT + 2
    today = datetime.date.today().isoformat()
    return {
        "width": WIDTH,
        "col_width": COL_WIDTH,
        "height": footer_y + 20,
        "footer_y": footer_y,
        "title": "Follow-up of issues and pull requests",
        "subtitle": "pydoe and eggzec, bots excluded",
        "footer": f"Counts cover all public repositories of both organisations. Source: GitHub, {today}.",
        "colors": COLORS,
        "columns": columns,
        "font_regular": font("Regular"),
        "font_semibold": font("SemiBold"),
    }


def main() -> None:
    env = Environment(
        loader=FileSystemLoader(HERE),
        autoescape=select_autoescape(["j2", "svg"], default_for_string=True),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template("card.svg.j2")
    context = build_context()
    out = ROOT / "metrics"
    out.mkdir(exist_ok=True)
    for theme, vars_ in THEMES.items():
        svg = template.render(**context, theme={"vars": vars_})
        (out / f"status-{theme}.svg").write_text(svg)
        print(f"wrote metrics/status-{theme}.svg")


if __name__ == "__main__":
    main()
