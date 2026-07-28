"""Chemins par défaut de l'état local d'EdgeLab (registre, lockbox).

Centralisé ici pour que chaque commande CLI pointe vers le même défaut sans
dupliquer la constante, tout en restant libre de le surcharger (tests,
environnements multiples).
"""

from pathlib import Path

DEFAULT_STATE_DIR = Path(".edgelab")
DEFAULT_REGISTRY_DB = DEFAULT_STATE_DIR / "registry.sqlite3"
DEFAULT_LOCKBOX_DB = DEFAULT_STATE_DIR / "lockbox.sqlite3"
