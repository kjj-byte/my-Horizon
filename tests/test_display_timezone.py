"""display.timezone decides which calendar day a summary is dated with."""

import pytest
from pydantic import ValidationError

from src.models import Config

MINIMAL_CONFIG = {
    "ai": {"provider": "openai", "model": "test", "api_key_env": "OPENAI_API_KEY"},
    "sources": {},
}


def _config(display: dict) -> Config:
    return Config.model_validate({**MINIMAL_CONFIG, "display": display})


def test_timezone_defaults_to_utc():
    assert _config({}).display.timezone == "UTC"


def test_timezone_accepts_iana_name():
    assert _config({"timezone": "Asia/Shanghai"}).display.timezone == "Asia/Shanghai"


@pytest.mark.parametrize("value", ["Asia/Shanghaii", "not a zone", ""])
def test_timezone_rejects_unknown_name(value):
    with pytest.raises(ValidationError):
        _config({"timezone": value})