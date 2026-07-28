"""Accès append-only au registre d'essais (I1), adossé à SQLite.

Le garde-fou contre la mutation est à deux niveaux : ce repository n'expose
aucune méthode `update`/`delete`, et la table SQLite elle-même refuse toute
mutation via des triggers `BEFORE UPDATE`/`BEFORE DELETE` — même du code qui
contournerait ce repository et parlerait à la base directement ne peut pas
altérer un essai déjà écrit.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from types import TracebackType

from edgelab.registry.models import Trial, TrialType

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS trials (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    trial_type TEXT NOT NULL,
    strategy_id TEXT NOT NULL,
    code_hash TEXT NOT NULL,
    params_json TEXT NOT NULL,
    params_hash TEXT NOT NULL,
    dataset_hash TEXT NOT NULL,
    lineage_hash TEXT NOT NULL,
    metrics_json TEXT NOT NULL,
    artifacts_path TEXT,
    note TEXT NOT NULL DEFAULT ''
);

CREATE TRIGGER IF NOT EXISTS trials_no_update
BEFORE UPDATE ON trials
BEGIN
    SELECT RAISE(ABORT, 'edgelab: le registre des essais est append-only (I1)');
END;

CREATE TRIGGER IF NOT EXISTS trials_no_delete
BEFORE DELETE ON trials
BEGIN
    SELECT RAISE(ABORT, 'edgelab: le registre des essais est append-only (I1)');
END;
"""


class TrialRepositoryError(RuntimeError):
    """Erreur levée par une opération invalide sur le registre d'essais."""


class TrialRepository:
    """Registre d'essais append-only. Seule `record` écrit ; rien ne se supprime."""

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

    def __enter__(self) -> TrialRepository:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def record(self, trial: Trial) -> None:
        """Écrit un essai. Seule opération d'écriture exposée par le registre.

        Raises:
            TrialRepositoryError: si un essai avec le même `id` existe déjà.
        """
        try:
            self._conn.execute(
                """
                INSERT INTO trials (
                    id, created_at, trial_type, strategy_id, code_hash,
                    params_json, params_hash, dataset_hash, lineage_hash,
                    metrics_json, artifacts_path, note
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trial.id,
                    trial.created_at.isoformat(),
                    trial.trial_type.value,
                    trial.strategy_id,
                    trial.code_hash,
                    json.dumps(trial.params, sort_keys=True, default=str),
                    trial.params_hash,
                    trial.dataset_hash,
                    trial.lineage_hash,
                    json.dumps(trial.metrics, sort_keys=True),
                    trial.artifacts_path,
                    trial.note,
                ),
            )
            self._conn.commit()
        except sqlite3.IntegrityError as exc:
            raise TrialRepositoryError(f"trial '{trial.id}' already recorded") from exc
        logger.info(
            "trial recorded id=%s type=%s strategy=%s",
            trial.id,
            trial.trial_type.value,
            trial.strategy_id,
        )

    def get(self, trial_id: str) -> Trial | None:
        """Renvoie l'essai `trial_id`, ou `None` s'il n'existe pas."""
        row = self._conn.execute("SELECT * FROM trials WHERE id = ?", (trial_id,)).fetchone()
        return None if row is None else _row_to_trial(row)

    def list_trials(self) -> list[Trial]:
        """Renvoie tous les essais, du plus récent au plus ancien."""
        rows = self._conn.execute("SELECT * FROM trials ORDER BY created_at DESC").fetchall()
        return [_row_to_trial(row) for row in rows]


def _row_to_trial(row: sqlite3.Row) -> Trial:
    return Trial(
        id=row["id"],
        created_at=datetime.fromisoformat(row["created_at"]),
        trial_type=TrialType(row["trial_type"]),
        strategy_id=row["strategy_id"],
        code_hash=row["code_hash"],
        params=json.loads(row["params_json"]),
        params_hash=row["params_hash"],
        dataset_hash=row["dataset_hash"],
        lineage_hash=row["lineage_hash"],
        metrics=json.loads(row["metrics_json"]),
        artifacts_path=row["artifacts_path"],
        note=row["note"],
    )
