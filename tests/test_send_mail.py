"""Email helper: the address comes from the EMAIL_ADDRESS secret, not the repo."""

import pytest

from scripts.send_mail import mailbox


def test_requires_address(monkeypatch):
    monkeypatch.delenv("EMAIL_ADDRESS", raising=False)

    with pytest.raises(RuntimeError, match="EMAIL_ADDRESS"):
        mailbox()


def test_reads_address(monkeypatch):
    monkeypatch.setenv("EMAIL_ADDRESS", "owner@example.com")

    assert mailbox() == "owner@example.com"