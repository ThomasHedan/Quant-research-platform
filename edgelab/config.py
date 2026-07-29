"""Chemins par défaut de l'état local d'EdgeLab (registre, lockbox).

Centralisé ici pour que chaque commande CLI pointe vers le même défaut sans
dupliquer la constante, tout en restant libre de le surcharger (tests,
environnements multiples).
"""

from pathlib import Path

DEFAULT_STATE_DIR = Path(".edgelab")
DEFAULT_REGISTRY_DB = DEFAULT_STATE_DIR / "registry.sqlite3"
DEFAULT_LOCKBOX_DB = DEFAULT_STATE_DIR / "lockbox.sqlite3"
DEFAULT_PAPERS_DB = DEFAULT_STATE_DIR / "papers.sqlite3"

DEFAULT_DATA_DIR = DEFAULT_STATE_DIR / "data"
DEFAULT_DATASET_CATALOG = DEFAULT_DATA_DIR / "catalog.duckdb"
DEFAULT_BARS_DIR = DEFAULT_DATA_DIR / "bars"
DEFAULT_DOWNLOAD_DIR = DEFAULT_DATA_DIR / "downloads"
"""Artefacts bruts du fournisseur, conservés à côté du store normalisé (voir `data/README.md`)."""
