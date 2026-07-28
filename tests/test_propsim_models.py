"""Tests de edgelab.propsim.models (Phase 5)."""

from collections.abc import Callable
from datetime import date

import pytest
from edgelab.propsim.models import (
    ChallengePhase,
    DailyLossGuard,
    PropFirmRuleset,
)


def test_ruleset_is_verified_when_date_and_source_are_set(
    make_ruleset: Callable[..., PropFirmRuleset],
) -> None:
    """Un ruleset avec date de vérification et URL de source est vérifié."""
    ruleset = make_ruleset(verified_at=date(2026, 1, 1), source_url="https://example.com")

    assert ruleset.is_verified is True


def test_ruleset_is_not_verified_without_verification_date(
    make_ruleset: Callable[..., PropFirmRuleset],
) -> None:
    """Un ruleset sans date de vérification est marqué non vérifié, même avec une source."""
    ruleset = make_ruleset(verified_at=None, source_url="https://example.com")

    assert ruleset.is_verified is False


def test_ruleset_is_not_verified_without_source_url(
    make_ruleset: Callable[..., PropFirmRuleset],
) -> None:
    """Un ruleset sans URL de source est marqué non vérifié, même avec une date."""
    ruleset = make_ruleset(verified_at=date(2026, 1, 1), source_url=None)

    assert ruleset.is_verified is False


def test_ruleset_phase_returns_matching_phase(
    make_ruleset: Callable[..., PropFirmRuleset], make_phase: Callable[..., ChallengePhase]
) -> None:
    """`phase()` retrouve le palier par son nom."""
    ruleset = make_ruleset(phases=(make_phase(name="challenge"), make_phase(name="verification")))

    assert ruleset.phase("verification").name == "verification"


def test_ruleset_phase_raises_for_unknown_name(
    make_ruleset: Callable[..., PropFirmRuleset],
) -> None:
    """Demander un palier inexistant lève une erreur explicite plutôt que renvoyer None."""
    ruleset = make_ruleset()

    with pytest.raises(KeyError, match="inconnu"):
        ruleset.phase("does-not-exist")


def test_ruleset_requires_at_least_one_phase(make_phase: Callable[..., ChallengePhase]) -> None:
    """Un ruleset sans aucun palier n'a pas de sens."""
    with pytest.raises(ValueError, match="phases"):
        PropFirmRuleset(firm_name="x", ruleset_name="y", phases=())


def test_daily_loss_guard_disabled_by_default() -> None:
    """Le garde-fou de perte journalière est désactivé par défaut."""
    guard = DailyLossGuard()

    assert guard.enabled is False


def test_daily_loss_guard_rejects_zero_threshold_when_enabled() -> None:
    """Un garde-fou actif sans seuil positif ne protège rien : c'est une erreur de config."""
    with pytest.raises(ValueError, match="threshold_pct"):
        DailyLossGuard(enabled=True, threshold_pct=0.0)


def test_restrictions_default_to_unknown_not_false(
    make_ruleset: Callable[..., PropFirmRuleset],
) -> None:
    """Les restrictions non sourcées sont `None` (inconnu), jamais devinées à `False`."""
    ruleset = make_ruleset()

    assert ruleset.restrictions.news_trading_allowed is None
    assert ruleset.restrictions.weekend_allowed is None
