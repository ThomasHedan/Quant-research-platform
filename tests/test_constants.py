"""Constantes partagées par la suite de tests (seuils statistiques, tolérances).

Peuplé au fur et à mesure que les modules statistiques (research, validation,
propsim) atterrissent — voir CLAUDE.md pour l'ordre des phases.
"""

SAMPLE_STRATEGY_CODE = b"def signal(bar):\n    return bar.close > bar.open\n"
SAMPLE_PARAMS = {"horizon": 10, "threshold": 0.5}
SAMPLE_DATASET_HASH = "a" * 64
