from datetime import datetime, timezone
from types import SimpleNamespace

from src.models import (
    ClassificationResult,
    ContentAnalysis,
    ContentItem,
    ProcessingConfig,
    ProcessingResult,
    ProfileSettingsConfig,
    SourceType,
)
from src.orchestrator import HorizonOrchestrator


def make_item(item_id: str, title: str, url: str, content: str | None = None) -> ContentItem:
    return ContentItem(
        id=item_id,
        source_type=SourceType.RSS,
        title=title,
        url=url,
        content=content,
        published_at=datetime.now(timezone.utc),
        profile="cloud-perks",
        processing=ProcessingResult(
            classification=ClassificationResult(
                profile="cloud-perks", method="source_override"
            ),
            analysis=ContentAnalysis(score=9.0, reason="test", summary=title),
        ),
    )


def make_orchestrator(settings: ProfileSettingsConfig) -> HorizonOrchestrator:
    orchestrator = HorizonOrchestrator.__new__(HorizonOrchestrator)
    orchestrator.config = SimpleNamespace(
        processing=ProcessingConfig(profile_settings={"cloud-perks": settings})
    )
    return orchestrator


def test_excludes_drop_grey_market_and_squatted_mirrors():
    orchestrator = make_orchestrator(
        ProfileSettingsConfig(
            threshold=5.0,
            exclude_url_substrings=["zssou.com"],
            exclude_keywords=["注册机"],
        )
    )
    assert not orchestrator.passes_profile_filter(
        make_item("a", "ChatGPT 注册机教程", "https://example.com/a")
    )
    assert not orchestrator.passes_profile_filter(
        make_item("b", "Gemini 免费额度", "https://zssou.com/b", "正文提到注册机")
    )
    assert orchestrator.passes_profile_filter(
        make_item("c", "Gemini 学生免费一年", "https://blog.google/c")
    )


def test_no_excludes_configured_keeps_old_behavior():
    orchestrator = make_orchestrator(ProfileSettingsConfig(threshold=5.0))
    assert orchestrator.passes_profile_filter(
        make_item("a", "ChatGPT 注册机教程", "https://zssou.com/a")
    )