"""Constantes partagées par la suite de tests (seuils statistiques, tolérances).

Peuplé au fur et à mesure que les modules statistiques (research, validation,
propsim) atterrissent — voir CLAUDE.md pour l'ordre des phases.
"""

SAMPLE_STRATEGY_CODE = b"def signal(bar):\n    return bar.close > bar.open\n"
SAMPLE_PARAMS = {"horizon": 10, "threshold": 0.5}
SAMPLE_DATASET_HASH = "a" * 64

# Phase 1 : données et coûts
BAR_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume")

# Fournisseur London Strategic Edge
LSE_TIMEFRAME_COUNT = 14
"""Le vault documente quatorze résolutions de barres, de `1s` à `1mo`."""

RED_FLAG_ACCESS_COUNT = 3
"""Nombre d'accès holdout à partir duquel l'UI doit lever un drapeau rouge (I3)."""
