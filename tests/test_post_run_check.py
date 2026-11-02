"""Post-run check: the verdict logic that decides whether to alarm."""

from zoneinfo import ZoneInfo

from scripts.post_run_check import build_body, display_timezone, today_runs, verdict

BJ = ZoneInfo("Asia/Shanghai")
TODAY = "2026-11-02"


def _run(
    event="workflow_dispatch",
    created="2026-11-01T23:00:00Z",
    conclusion="success",
    run_id=1,
):
    return {
        "id": run_id,
        "path": ".github/workflows/daily-summary.yml",
        "event": event,
        "created_at": created,
        "conclusion": conclusion,
        "status": "completed",
    }


def test_run_at_23_utc_belongs_to_the_next_beijing_day():
    assert [r["event"] for r in today_runs([_run()], TODAY, BJ)] == ["workflow_dispatch"]


def test_yesterdays_run_is_ignored():
    assert today_runs([_run(created="2026-10-31T23:00:00Z")], TODAY, BJ) == []


def test_other_workflows_are_ignored():
    other = {**_run(), "path": ".github/workflows/deploy-docs.yml"}

    assert today_runs([other], TODAY, BJ) == []


def test_healthy_day_has_no_problems():
    lines, problems = verdict([_run()], {"size": 34794}, TODAY, BJ)

    assert problems == []
    assert any("已发布" in line for line in lines)
    assert "✅" in build_body(lines, problems, "me/repo")


def test_missing_post_is_a_problem():
    _, problems = verdict([_run()], None, TODAY, BJ)

    assert problems == ["gh-pages 上没有 _posts/2026-11-02-summary-zh.md"]


def test_cron_that_really_ran_is_a_problem():
    cron = _run(event="schedule", created="2026-11-02T00:30:00Z", run_id=2)

    _, problems = verdict([_run(), cron], {"size": 1}, TODAY, BJ, {2: "success"})

    assert any("cron 没有被去重跳过" in problem for problem in problems)


def test_cron_skipped_at_job_level_is_healthy():
    """A skipped job still leaves the workflow run's own conclusion at success."""
    cron = _run(event="schedule", created="2026-11-02T00:30:00Z", run_id=2)

    lines, problems = verdict([_run(), cron], {"size": 1}, TODAY, BJ, {2: "skipped"})

    assert problems == []
    assert any("skipped（去重）" in line for line in lines)


def test_unknown_job_state_is_not_alarmed():
    cron = _run(event="schedule", created="2026-11-02T00:30:00Z", run_id=3)

    lines, problems = verdict([_run(), cron], {"size": 1}, TODAY, BJ, {})

    assert problems == []
    assert any("无法确认" in line for line in lines)


def test_no_runs_today_is_a_problem():
    _, problems = verdict([], {"size": 1}, TODAY, BJ)

    assert any("还没有 Daily Horizon Summary 运行记录" in p for p in problems)


def test_timezone_falls_back_when_config_is_missing(tmp_path):
    assert display_timezone(str(tmp_path / "missing.json")) == "Asia/Shanghai"


def test_timezone_comes_from_config(tmp_path):
    config = tmp_path / "config.json"
    config.write_text('{"display": {"timezone": "Asia/Tokyo"}}', encoding="utf-8")

    assert display_timezone(str(config)) == "Asia/Tokyo"


def test_tokyo_zone_shifts_the_day():
    # 15:30Z is 23:30 the previous day in Shanghai but 00:30 today in Tokyo.
    late = _run(created="2026-11-01T15:30:00Z")

    assert len(today_runs([late], TODAY, ZoneInfo("Asia/Tokyo"))) == 1
    assert today_runs([late], TODAY, ZoneInfo("Asia/Shanghai")) == []