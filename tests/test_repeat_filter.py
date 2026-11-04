"""Repeat filter: links from the previous digests must not be republished."""

from datetime import date, timedelta

from src.processing.repeat_filter import digest_url_key, recent_digest_urls

TODAY = date(2026, 11, 2)


def _post(path, items, day):
    body = "---\nlayout: default\n---\n\n> summary line\n\n"
    for title, url in items:
        body += f"## [{title}]({url})\n\nSomething about it.\n\n"
    (path / f"{day}-summary-zh.md").write_text(body, encoding="utf-8")


def test_only_previous_three_days_count(tmp_path):
    _post(tmp_path, [("today", "https://example.com/today")], TODAY)
    _post(tmp_path, [("y1", "https://example.com/y1")], TODAY - timedelta(days=1))
    _post(tmp_path, [("y3", "https://example.com/y3")], TODAY - timedelta(days=3))
    _post(tmp_path, [("y4", "https://example.com/y4")], TODAY - timedelta(days=4))

    urls = recent_digest_urls(tmp_path, TODAY)

    assert urls == {"https://example.com/y1", "https://example.com/y3"}


def test_same_link_is_matched_through_noise(tmp_path):
    _post(
        tmp_path,
        [("昨天", "https://Example.com/story/#top")],
        TODAY - timedelta(days=1),
    )

    urls = recent_digest_urls(tmp_path, TODAY)

    assert digest_url_key("https://example.com/story") in urls


def test_html_escaped_link_matches_plain_url(tmp_path):
    """Posts escape `&` as `&amp;`; the fetched item URL does not."""
    _post(
        tmp_path,
        [("昨天", "https://example.com/story?a=1&amp;b=2")],
        TODAY - timedelta(days=1),
    )

    urls = recent_digest_urls(tmp_path, TODAY)

    assert digest_url_key("https://example.com/story?a=1&b=2") in urls


def test_unrelated_files_are_ignored(tmp_path):
    (tmp_path / "notes.md").write_text("## [x](https://example.com/notes)", encoding="utf-8")
    (tmp_path / "2026-13-40-summary-zh.md").write_text(
        "## [bad](https://example.com/bad)", encoding="utf-8"
    )

    assert recent_digest_urls(tmp_path, TODAY) == set()


def test_missing_directory_is_empty(tmp_path):
    assert recent_digest_urls(tmp_path / "missing", TODAY) == set()