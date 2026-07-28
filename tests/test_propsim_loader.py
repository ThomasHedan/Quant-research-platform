"""Tests de edgelab.propsim.loader (Phase 5) et des rulesets livrés."""

from pathlib import Path

import pytest
import yaml
from edgelab.propsim.loader import RULESETS_DIR, load_ruleset, load_shipped_rulesets
from edgelab.propsim.models import PropFirmRuleset


def test_load_ruleset_parses_a_valid_yaml_file(tmp_path: Path) -> None:
    """Un YAML valide au regard du schéma se charge en `PropFirmRuleset`."""
    path = tmp_path / "test.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "firm_name": "Acme",
                "ruleset_name": "Acme Challenge",
                "phases": [
                    {
                        "name": "challenge",
                        "profit_target_pct": 0.1,
                        "max_daily_loss_pct": 0.05,
                        "max_drawdown_pct": 0.1,
                        "drawdown_type": "static",
                        "drawdown_basis": "balance",
                        "min_trading_days": 4,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    ruleset = load_ruleset(path)

    assert ruleset.firm_name == "Acme"
    assert ruleset.is_verified is False


def test_load_ruleset_rejects_a_schema_violation(tmp_path: Path) -> None:
    """Un YAML sans palier est refusé par la validation Pydantic."""
    path = tmp_path / "invalid.yaml"
    path.write_text(yaml.safe_dump({"firm_name": "Acme", "ruleset_name": "x", "phases": []}))

    with pytest.raises(ValueError, match="phases"):
        load_ruleset(path)


def test_load_shipped_rulesets_returns_all_four_firms() -> None:
    """Les quatre rulesets requis par la spec (FTMO, The5ers, FundingPips, Topstep) se chargent."""
    rulesets = load_shipped_rulesets()

    assert set(rulesets) == {"ftmo", "the5ers", "fundingpips", "topstep"}
    assert all(isinstance(r, PropFirmRuleset) for r in rulesets.values())


def test_shipped_ftmo_ruleset_is_verified() -> None:
    """Le ruleset FTMO est sourcé sur une page officielle et daté : il est vérifié."""
    ruleset = load_ruleset(RULESETS_DIR / "ftmo.yaml")

    assert ruleset.is_verified is True
    assert ruleset.source_url is not None
    assert "ftmo.com" in ruleset.source_url


@pytest.mark.parametrize("filename", ["topstep.yaml", "fundingpips.yaml", "the5ers.yaml"])
def test_shipped_unverified_rulesets_are_flagged_and_documented(filename: str) -> None:
    """Un ruleset dont les chiffres n'ont pas pu être confirmés sur une source officielle
    directement lue par Claude Code est marqué non vérifié et son `note` l'explique."""
    ruleset = load_ruleset(RULESETS_DIR / filename)

    assert ruleset.is_verified is False
    assert "UNVERIFIED" in ruleset.note
