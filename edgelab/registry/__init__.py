"""Registre d'essais append-only (I1) : hashing du lineage
(code + params + dataset), garde-fou contre UPDATE/DELETE."""

from edgelab.registry.hashing import compute_lineage_hash, hash_bytes, hash_file, hash_params
from edgelab.registry.models import Trial, TrialType
from edgelab.registry.repository import TrialRepository, TrialRepositoryError

__all__ = [
    "Trial",
    "TrialRepository",
    "TrialRepositoryError",
    "TrialType",
    "compute_lineage_hash",
    "hash_bytes",
    "hash_file",
    "hash_params",
]
