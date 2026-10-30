"""Guard: a whole batch of failed AI analyses must fail loudly, not publish empties."""

from types import SimpleNamespace

import pytest

from src.orchestrator import _analysis_succeeded, _raise_if_all_analysis_failed


def _item(score):
    analysis = None if score is None else SimpleNamespace(score=score)
    return SimpleNamespace(processing=SimpleNamespace(analysis=analysis))


def test_analysis_succeeded_true_for_scored_item():
    assert _analysis_succeeded(_item(7.5)) is True


@pytest.mark.parametrize(
    "item",
    [
        SimpleNamespace(processing=None),
        SimpleNamespace(processing=SimpleNamespace(analysis=None)),
        _item(None),
    ],
)
def test_analysis_succeeded_false_when_no_score(item):
    assert _analysis_succeeded(item) is False


def test_raises_when_every_item_failed():
    with pytest.raises(RuntimeError, match="refusing to publish"):
        _raise_if_all_analysis_failed([_item(None), _item(None)])


def test_returns_failure_count_for_partial_failure():
    assert _raise_if_all_analysis_failed([_item(8.0), _item(None)]) == 1


def test_empty_batch_is_not_an_error():
    assert _raise_if_all_analysis_failed([]) == 0
