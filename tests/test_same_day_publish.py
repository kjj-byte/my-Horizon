"""Same-day publishes: one digest per local day, whatever triggered the run."""

from datetime import date, timedelta

from src.processing.repeat_filter import published_today, recent_digest_urls


def _post(path, items, day):
    body = "> summary\n\n"
    for title, url in items:
        body += f"### [{title}]({url})\n\ntext\n\n"
    (path / f"{day}-summary-zh.md").write_text(body, encoding="utf-8")


TODAY = date(2026, 11, 5)


def test_published_today_sees_the_restored_post(tmp_path):
    _post(tmp_path, [("a", "https://example.com/a")], TODAY)

    assert published_today(tmp_path, TODAY)
    assert not published_today(tmp_path, TODAY + timedelta(days=1))
    assert not published_today(tmp_path / "missing", TODAY)


def test_published_today_ignores_unparseable_names(tmp_path):
    (tmp_path / "notes.md").write_text("### [x](https://example.com/x)", encoding="utf-8")

    assert not published_today(tmp_path, TODAY)


def test_second_run_drops_todays_items(tmp_path):
    """11-05 published twice: the 07:30 rerun re-listed the 06:00 digest."""
    _post(tmp_path, [("a", "https://example.com/a")], TODAY)
    _post(tmp_path, [("b", "https://example.com/b")], TODAY - timedelta(days=1))

    urls = recent_digest_urls(tmp_path, TODAY, include_today=True)

    assert urls == {"https://example.com/a", "https://example.com/b"}


def test_first_run_does_not_drop_todays_items(tmp_path):
    """A re-run of a day that never published must not filter everything out."""
    _post(tmp_path, [("a", "https://example.com/a")], TODAY)

    assert recent_digest_urls(tmp_path, TODAY) == set()


def test_orchestrator_skips_when_today_is_published(monkeypatch, capsys):
    """The app-level guard stops a same-day rerun before any token is spent."""
    import asyncio
    from types import SimpleNamespace

    from src import orchestrator as orch_mod

    orch = object.__new__(orch_mod.HorizonOrchestrator)
    orch.icons = {"start": ""}
    orch.console = SimpleNamespace(print=lambda *a, **k: print(*a))
    monkeypatch.setattr(orch_mod.HorizonOrchestrator, "today_already_published", lambda self: True)

    asyncio.run(orch.run())

    assert "Already published a digest for today" in capsys.readouterr().out