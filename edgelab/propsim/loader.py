"""Chargement des rulesets déclaratifs (YAML) de prop firms (Phase 5).

Un ruleset est un fichier YAML, pas du code : ajouter une firme ou corriger
un chiffre ne demande jamais de toucher au moteur de simulation.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from edgelab.propsim.models import PropFirmRuleset

RULESETS_DIR = Path(__file__).parent / "rulesets"


def load_ruleset(path: Path) -> PropFirmRuleset:
    """Charge et valide un ruleset depuis un fichier YAML.

    Raises:
        ValueError: si le contenu est invalide au regard du schéma `PropFirmRuleset`.
    """
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return PropFirmRuleset.model_validate(raw)


def load_shipped_rulesets() -> dict[str, PropFirmRuleset]:
    """Charge les rulesets livrés avec EdgeLab, indexés par nom de fichier (sans extension)."""
    return {p.stem: load_ruleset(p) for p in sorted(RULESETS_DIR.glob("*.yaml"))}
