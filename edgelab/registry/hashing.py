"""Hashing du lineage d'un essai (I1) : code, paramètres, dataset.

Le hash doit être déterministe et sensible au moindre octet : c'est ce qui
permet au registre de distinguer une ré-exécution à l'identique d'un essai
qui a réellement changé. Sans cette propriété, le nombre d'essais lu par le
Deflated Sharpe Ratio (Phase 4) ne veut plus rien dire.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def hash_bytes(data: bytes) -> str:
    """Hash SHA-256 hexadécimal d'un contenu brut."""
    return hashlib.sha256(data).hexdigest()


def hash_file(path: Path) -> str:
    """Hash SHA-256 du contenu d'un fichier (ex. code source d'une stratégie)."""
    return hash_bytes(path.read_bytes())


def hash_params(params: dict[str, Any]) -> str:
    """Hash SHA-256 d'un dict de paramètres.

    La sérialisation JSON est canonique (`sort_keys=True`, séparateurs fixes)
    pour que l'ordre d'insertion du dict n'affecte jamais le hash produit.
    """
    canonical = json.dumps(params, sort_keys=True, separators=(",", ":"), default=str)
    return hash_bytes(canonical.encode("utf-8"))


def compute_lineage_hash(*, code_hash: str, params_hash: str, dataset_hash: str) -> str:
    """Combine code, paramètres et dataset en le hash de lineage d'un essai.

    Deux essais partageant le même triplet (code, params, dataset) produisent
    le même lineage ; changer un seul des trois — y compris un octet du
    fichier de stratégie — le change.
    """
    combined = f"{code_hash}:{params_hash}:{dataset_hash}"
    return hash_bytes(combined.encode("utf-8"))
