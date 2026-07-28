"""Lockbox du holdout (I3).

Le holdout n'est jamais accessible par un chemin de code générique : cette
classe est le seul point d'entrée. Chaque accès exige une raison écrite non
vide et est journalisé de façon permanente — le journal est, comme le
registre d'essais, protégé contre `UPDATE`/`DELETE` au niveau SQLite. Le
compteur qui en résulte (`access_count`) est ce que l'UI affichera à côté de
chaque stratégie ; il n'existe aucune méthode pour le remettre à zéro.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType

logger = logging.getLogger(__name__)

RED_FLAG_THRESHOLD = 3
"""Nombre d'accès holdout à partir duquel une stratégie doit être signalée en rouge dans l'UI."""

_SCHEMA = """
CREATE TABLE IF NOT EXISTS holdout_access (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    accessed_at TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS holdout_access_no_update
BEFORE UPDATE ON holdout_access
BEGIN
    SELECT RAISE(ABORT, 'edgelab: le journal d''acces au holdout est append-only (I3)');
END;

CREATE TRIGGER IF NOT EXISTS holdout_access_no_delete
BEFORE DELETE ON holdout_access
BEGIN
    SELECT RAISE(ABORT, 'edgelab: le journal d''acces au holdout est append-only (I3)');
END;
"""


class HoldoutAccessDeniedError(RuntimeError):
    """Levée quand un accès au holdout est tenté sans raison écrite."""


@dataclass(frozen=True)
class HoldoutAccessRecord:
    """Une ligne du journal d'accès au holdout."""

    strategy_id: str
    reason: str
    accessed_at: datetime


class HoldoutLockbox:
    """Point d'entrée unique et journalisé pour accéder au holdout d'une stratégie."""

    def __init__(self, db_path: Path | str) -> None:
        self._db_path = str(db_path)
        if self._db_path != ":memory:":
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        """Ferme la connexion SQLite sous-jacente."""
        self._conn.close()

    def __enter__(self) -> HoldoutLockbox:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def access(self, strategy_id: str, reason: str) -> int:
        """Journalise un accès au holdout et renvoie le nouveau compteur.

        Raises:
            HoldoutAccessDeniedError: si `reason` est vide ou ne contient que
                des espaces.
        """
        reason = reason.strip()
        if not reason:
            raise HoldoutAccessDeniedError(
                f"accès au holdout refusé pour '{strategy_id}' : raison écrite obligatoire (I3)"
            )
        self._conn.execute(
            "INSERT INTO holdout_access (strategy_id, reason, accessed_at) VALUES (?, ?, ?)",
            (strategy_id, reason, datetime.now(UTC).isoformat()),
        )
        self._conn.commit()
        count = self.access_count(strategy_id)
        logger.warning(
            "holdout accessed strategy=%s count=%d reason=%s", strategy_id, count, reason
        )
        return count

    def access_count(self, strategy_id: str) -> int:
        """Compteur d'accès permanent attaché à la stratégie."""
        row = self._conn.execute(
            "SELECT COUNT(*) FROM holdout_access WHERE strategy_id = ?", (strategy_id,)
        ).fetchone()
        return int(row[0])

    def is_flagged(self, strategy_id: str) -> bool:
        """Vrai à partir de `RED_FLAG_THRESHOLD` accès — le drapeau rouge de l'UI."""
        return self.access_count(strategy_id) >= RED_FLAG_THRESHOLD

    def access_log(self, strategy_id: str) -> list[HoldoutAccessRecord]:
        """Historique complet des accès pour une stratégie, du plus ancien au plus récent."""
        rows = self._conn.execute(
            "SELECT * FROM holdout_access WHERE strategy_id = ? ORDER BY id",
            (strategy_id,),
        ).fetchall()
        return [
            HoldoutAccessRecord(
                strategy_id=row["strategy_id"],
                reason=row["reason"],
                accessed_at=datetime.fromisoformat(row["accessed_at"]),
            )
            for row in rows
        ]
