"""Tests de edgelab.registry.models (I1)."""

from collections.abc import Callable

import pytest
from edgelab.registry.models import Trial
from pydantic import ValidationError


def test_trial_generates_id_and_timestamp_by_default(make_trial: Callable[..., Trial]) -> None:
    """Un `Trial` sans id/created_at explicites en génère automatiquement."""
    trial = make_trial()

    assert trial.id
    assert trial.created_at is not None


def test_trial_ids_are_unique_by_default(make_trial: Callable[..., Trial]) -> None:
    """Deux `Trial` construits sans id explicite ne collisionnent pas."""
    first = make_trial()
    second = make_trial()

    assert first.id != second.id


def test_trial_is_frozen(make_trial: Callable[..., Trial]) -> None:
    """Un `Trial` est immuable : toute tentative de mutation lève (I1)."""
    trial = make_trial()

    with pytest.raises(ValidationError):
        trial.note = "modifié après coup"  # type: ignore[misc]
