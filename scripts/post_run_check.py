"""Post-run check: did today's Horizon run publish, and did the dedupe work?

Run by .github/workflows/post-run-check.yml after the daily job. Prints a report
and emails the same text; exits non-zero when something looks wrong.
"""

from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from send_mail import send_mail  # noqa: E402  (script dir, not a package)

DEFAULT_TZ = "Asia/Shanghai"


def display_timezone(config_path: str = "data/config.github.json") -> str:
    """Same zone the digest is dated with; never hardcode it in the workflow."""
    try:
        with open(config_path, encoding="utf-8") as handle:
            return json.load(handle)["display"]["timezone"]
    except (OSError, ValueError, KeyError):
        return DEFAULT_TZ


def gh_json(path: str) -> Any:
    result = subprocess.run(
        ["gh", "api", path], capture_output=True, text=True, encoding="utf-8"
    )
    if result.returncode != 0:
        return None
    return json.loads(result.stdout)


def today_runs(runs: list[dict], today: str, zone: ZoneInfo) -> list[dict]:
    """Today's runs in the display zone, so a cron delayed by hours still counts."""
    picked = []
    for run in runs:
        if not run.get("path", "").endswith("daily-summary.yml"):
            continue
        created = datetime.datetime.fromisoformat(
            run["created_at"].replace("Z", "+00:00")
        ).astimezone(zone)
        if created.strftime("%Y-%m-%d") == today:
            picked.append(run)
    picked.sort(key=lambda item: item["created_at"])
    return picked


def verdict(
    runs: list[dict], post: dict | None, today: str, zone: ZoneInfo
) -> tuple[list[str], list[str]]:
    """Return (report lines, problems). Problems make the check fail."""
    lines: list[str] = []
    problems: list[str] = []

    for run in runs:
        created = datetime.datetime.fromisoformat(
            run["created_at"].replace("Z", "+00:00")
        ).astimezone(zone)
        state = run.get("conclusion") or run.get("status")
        lines.append(f"- {run['event']} @ {created.strftime('%H:%M')} 北京 -> {state}")
    if not runs:
        problems.append("今天还没有 Daily Horizon Summary 运行记录")

    if post is None:
        problems.append(f"gh-pages 上没有 _posts/{today}-summary-zh.md")
    else:
        lines.append(f"- 已发布 _posts/{today}-summary-zh.md（{post.get('size', 0)} 字节）")

    cron = [run for run in runs if run["event"] == "schedule"]
    if not cron:
        lines.append("- 兜底 cron 今天还没排到（GitHub 排队延迟，不算失败）")
    elif all(run.get("conclusion") == "skipped" for run in cron):
        lines.append("- 兜底 cron 被 preflight 跳过，去重窗口生效")
    else:
        lines.append("- 兜底 cron 实际跑了一轮：可能与 07:00 那轮重复")
        problems.append("cron 没有被去重跳过（窗口或日期判定可能失效）")

    return lines, problems


def build_body(lines: list[str], problems: list[str], repo: str) -> str:
    state = "❌ 有问题" if problems else "✅ 正常"
    body = "\n".join([f"Horizon 跑完自检：{state}", "", *lines, ""])
    if problems:
        body += "问题：\n" + "\n".join(f"- {problem}" for problem in problems) + "\n"
    return body + f"\n运行记录：https://github.com/{repo}/actions\n"


def send_email(subject: str, body: str) -> None:
    send_mail(subject, body)


def main() -> int:
    # The report contains ✅/❌; a Windows console defaults to GBK and would crash.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    zone = ZoneInfo(display_timezone())
    today = datetime.datetime.now(zone).strftime("%Y-%m-%d")
    until = os.environ.get("CHECK_UNTIL", "").strip()
    if os.environ.get("EVENT") == "schedule" and until and today > until:
        print(f"CHECK_UNTIL={until} passed (today {today}); nothing to check.")
        return 0

    repo = os.environ["REPO"]
    runs = (gh_json(f"repos/{repo}/actions/runs?per_page=50") or {}).get(
        "workflow_runs", []
    )
    post = gh_json(f"repos/{repo}/contents/_posts/{today}-summary-zh.md?ref=gh-pages")
    lines, problems = verdict(today_runs(runs, today, zone), post, today, zone)
    body = build_body(lines, problems, repo)
    print(body)

    state = "❌ 有问题" if problems else "✅ 正常"
    try:
        send_email(f"Horizon 自检 {today}：{state}", body)
    except RuntimeError as error:
        print(f"{error}; email not sent")
        return 1
    print("SENT to EMAIL_ADDRESS")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())