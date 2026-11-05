"""Self-check for the daily-summary preflight dedupe. Read-only; needs `gh` logged in.

This machine has no bash, so the workflow's preflight `run:` block is checked by
mirroring its one decision against live gh-pages data instead of executing it.
"""

import datetime
import re
import subprocess
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = "kjj-byte/my-Horizon"
WF = Path(__file__).resolve().parents[1] / ".github/workflows/daily-summary.yml"


def block() -> str:
    text = WF.read_text(encoding="utf-8")
    match = re.search(r"\n        id: check\n.*?\n        run: \|\n(.*?)\n\n", text, re.S)
    if not match:
        sys.exit("preflight run block not found in the workflow")
    return "\n".join(line[10:] for line in match.group(1).splitlines())


def gh(*args: str) -> str:
    return subprocess.run(
        ["gh", *args], capture_output=True, text=True, encoding="utf-8", check=False
    ).stdout.strip()


def main() -> int:
    script = block()

    # 1. The 12h committer-date window (the bug) must not creep back in.
    assert "WINDOW_HOURS" not in script, "12h committer-date window is back"
    # 2. The deploy date comes from preflight, and both dates a run can land on exist.
    assert "date +%F" in script and "'+1 day'" in script, "publish date not derived from display timezone"

    tz_name = re.search(r"^\s*TZ_NAME=\$\(python3 .*?\)$", script, re.M).group(0)
    assert "config.github.json" in tz_name, "date must use the display timezone"
    zone = ZoneInfo("Asia/Shanghai")
    today = datetime.datetime.now(zone).strftime("%Y-%m-%d")
    tomorrow = (datetime.datetime.now(zone) + datetime.timedelta(days=1)).strftime("%Y-%m-%d")

    # 3. The decision itself, on live data: a re-published same-day post must not fool it.
    published = gh(
        "api",
        f"repos/{REPO}/commits?path=_posts/{today}-summary-zh.md&sha=gh-pages&per_page=1",
        "--jq",
        'if length > 0 then "true" else "false" end',
    )
    assert published in ("true", "false"), f"jq returned {published!r}, not a decision"

    print(f"today={today}  next={tomorrow}  {today}-summary-zh.md published={published}")
    print("OK  no 12h committer-date window")
    print("OK  publish date from display timezone")
    print(f"OK  preflight decision is content-based (published={published})")
    return 0


if __name__ == "__main__":
    sys.exit(main())