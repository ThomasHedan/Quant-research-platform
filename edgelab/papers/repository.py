"""Accès transactionnel aux fiches papier et à leur file de triage (Phase 7).

Contrairement au registre d'essais (I1) ou au journal d'accès holdout (I3),
rien ici n'impose l'append-only : un papier avance dans sa file de triage
(`TriageStatus`), et c'est une mutation attendue, pas une violation d'un
invariant. La fiche extraite (`PaperSheet`) reste, elle, immuable une fois
créée — la corriger crée un nouveau papier plutôt que de réécrire l'ancien.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType

from pydantic import BaseModel, ConfigDict

from edgelab.papers.models import (
    HypothesisDraft,
    HypothesisDraftRequest,
    PaperAnalysisRequest,
    PaperSheet,
    TriageStatus,
)
from edgelab.papers.testability import compute_testability_score
from edgelab.strategies.models import HypothesisSheet, KillCriterion

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
    id TEXT PRIMARY KEY,
    sheet_json TEXT NOT NULL,
    status TEXT NOT NULL,
    dead_reason TEXT NOT NULL DEFAULT '',
    hypothesis_draft_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


class PaperRepositoryError(RuntimeError):
    """Erreur levée par une opération invalide sur le stockage des papiers."""


class PaperNotFoundError(PaperRepositoryError):
    """Levée quand un `paper_id` référencé n'existe pas."""


class PaperRecord(BaseModel):
    """Un papier tel que lu depuis le stockage : fiche + position dans la file de triage."""

    model_config = ConfigDict(frozen=True)

    sheet: PaperSheet
    status: TriageStatus
    dead_reason: str
    hypothesis_draft: HypothesisDraft | None
    testability_score: float


def _strategy_id_for_draft(paper_id: str) -> str:
    """Identifiant de stratégie dérivé du papier — jamais fourni par l'IA externe."""
    return f"paper_{paper_id}"


class PaperRepository:
    """Stockage SQLite des fiches papier et de leur file de triage (Phase 7)."""

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

    def __enter__(self) -> PaperRepository:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def create(self, request: PaperAnalysisRequest) -> PaperRecord:
        """Crée une fiche papier à partir du JSON collé, directement en statut `fiche_faite`.

        Ce premier jet ne modélise pas l'état `a_lire` (un papier simplement
        repéré, pas encore dépouillé) : le flux implémenté part toujours
        d'une fiche déjà extraite par une IA externe. `a_lire` reste dans
        `TriageStatus` pour la complétude de la spec, mais rien ici n'y
        place de papier — voir `edgelab/papers/README.md`.
        """
        sheet = PaperSheet.from_request(request)
        now = datetime.now(UTC).isoformat()
        self._conn.execute(
            """
            INSERT INTO papers (id, sheet_json, status, dead_reason, hypothesis_draft_json,
                                 created_at, updated_at)
            VALUES (?, ?, ?, '', NULL, ?, ?)
            """,
            (sheet.id, sheet.model_dump_json(), TriageStatus.FICHE_FAITE.value, now, now),
        )
        self._conn.commit()
        logger.info("paper created id=%s title=%r", sheet.id, sheet.title)
        return PaperRecord(
            sheet=sheet,
            status=TriageStatus.FICHE_FAITE,
            dead_reason="",
            hypothesis_draft=None,
            testability_score=compute_testability_score(sheet),
        )

    def get(self, paper_id: str) -> PaperRecord | None:
        """Renvoie le papier `paper_id`, ou `None` s'il n'existe pas."""
        row = self._conn.execute("SELECT * FROM papers WHERE id = ?", (paper_id,)).fetchone()
        return None if row is None else _row_to_record(row)

    def list_papers(self) -> list[PaperRecord]:
        """Renvoie tous les papiers, du plus récemment mis à jour au plus ancien."""
        rows = self._conn.execute("SELECT * FROM papers ORDER BY updated_at DESC").fetchall()
        return [_row_to_record(row) for row in rows]

    def attach_hypothesis(self, paper_id: str, request: HypothesisDraftRequest) -> PaperRecord:
        """Rattache un brouillon d'hypothèse et fait avancer le papier à `hypothese_ecrite`.

        Construit un vrai `HypothesisSheet` (I2) à partir du JSON collé : la
        règle de falsifiabilité s'applique donc ici comme partout ailleurs,
        via le même modèle Pydantic. `strategy_id` et l'horodatage des
        critères de mort sont dérivés côté serveur, jamais acceptés depuis le
        JSON externe.

        Raises:
            PaperNotFoundError: si `paper_id` est inconnu.
        """
        existing = self.get(paper_id)
        if existing is None:
            raise PaperNotFoundError(f"paper '{paper_id}' introuvable")

        now = datetime.now(UTC)
        hypothesis = HypothesisSheet(
            strategy_id=_strategy_id_for_draft(paper_id),
            economic_hypothesis=request.economic_hypothesis,
            predicted_direction=request.predicted_direction,
            predicted_amplitude_atr=request.predicted_amplitude_atr,
            predicted_hit_rate=request.predicted_hit_rate,
            predicted_horizon_bars=request.predicted_horizon_bars,
            where_it_should_not_work=request.where_it_should_not_work,
            kill_criteria=tuple(
                KillCriterion(
                    name=c.name,
                    metric=c.metric,
                    comparison=c.comparison,
                    threshold=c.threshold,
                    recorded_at=now,
                )
                for c in request.kill_criteria
            ),
        )
        draft = HypothesisDraft(
            paper_id=paper_id,
            hypothesis=hypothesis,
            strategy_code_skeleton=request.strategy_code_skeleton,
        )
        self._conn.execute(
            "UPDATE papers SET hypothesis_draft_json = ?, status = ?, updated_at = ? WHERE id = ?",
            (
                draft.model_dump_json(),
                TriageStatus.HYPOTHESE_ECRITE.value,
                now.isoformat(),
                paper_id,
            ),
        )
        self._conn.commit()
        logger.info("hypothesis draft attached paper_id=%s", paper_id)
        return existing.model_copy(
            update={"status": TriageStatus.HYPOTHESE_ECRITE, "hypothesis_draft": draft}
        )

    def set_status(self, paper_id: str, status: TriageStatus, reason: str = "") -> PaperRecord:
        """Déplace un papier dans la file de triage.

        Raises:
            PaperNotFoundError: si `paper_id` est inconnu.
            PaperRepositoryError: si `status` est `mort` sans motif écrit —
                le motif de mort doit rester conservé (spec Phase 7).
        """
        existing = self.get(paper_id)
        if existing is None:
            raise PaperNotFoundError(f"paper '{paper_id}' introuvable")
        reason = reason.strip()
        if status is TriageStatus.MORT and not reason:
            raise PaperRepositoryError(
                f"impossible de marquer '{paper_id}' mort sans motif écrit (spec Phase 7)"
            )
        dead_reason = reason if status is TriageStatus.MORT else ""
        self._conn.execute(
            "UPDATE papers SET status = ?, dead_reason = ?, updated_at = ? WHERE id = ?",
            (status.value, dead_reason, datetime.now(UTC).isoformat(), paper_id),
        )
        self._conn.commit()
        logger.info("paper status changed id=%s status=%s", paper_id, status.value)
        return existing.model_copy(update={"status": status, "dead_reason": dead_reason})


def _row_to_record(row: sqlite3.Row) -> PaperRecord:
    sheet = PaperSheet.model_validate_json(row["sheet_json"])
    draft_json = row["hypothesis_draft_json"]
    draft = HypothesisDraft.model_validate_json(draft_json) if draft_json is not None else None
    return PaperRecord(
        sheet=sheet,
        status=TriageStatus(row["status"]),
        dead_reason=row["dead_reason"],
        hypothesis_draft=draft,
        testability_score=compute_testability_score(sheet),
    )
