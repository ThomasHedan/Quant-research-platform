"""Évaluation des critères de mort et cycle de vie d'une stratégie (Phase 4).

`evaluate_kill_criteria` lit la fiche d'hypothèse (I2) et rend un verdict
automatique critère par critère. `StrategyLifecycleRepository` applique ce
verdict : `DEAD` est un piège à sens unique appliqué au niveau SQL (même
garde-fou que le registre d'essais et la lockbox du holdout) — aucune
requête, même directe, ne peut faire redescendre une stratégie de `DEAD`
vers `CANDIDATE`. Retester l'idée exige une nouvelle fiche d'hypothèse
portant un nouveau `strategy_id`, dont le lien de parenté avec la stratégie
morte est conservé et interrogeable.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from types import TracebackType

from edgelab.strategies.models import HypothesisSheet, StrategyStatus
from edgelab.validation.models import KillCriteriaVerdict, KillCriterionVerdict

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS strategy_lifecycle (
    strategy_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    parent_strategy_id TEXT,
    updated_at TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS strategy_lifecycle_no_revival
BEFORE UPDATE OF status ON strategy_lifecycle
WHEN OLD.status = 'dead' AND NEW.status != 'dead'
BEGIN
    SELECT RAISE(ABORT, 'edgelab: une stratégie dead ne peut pas être remise en candidate');
END;
"""


class UnknownStrategyError(RuntimeError):
    """Levée quand une opération référence un `strategy_id` non enregistré."""


class DeadParentNotDeadError(RuntimeError):
    """Levée quand `parent_strategy_id` référence une stratégie qui n'est pas `dead`."""


def evaluate_kill_criteria(
    hypothesis: HypothesisSheet, measured_metrics: dict[str, float]
) -> KillCriteriaVerdict:
    """Évalue chaque critère de mort de `hypothesis` contre `measured_metrics`.

    Un critère dont la métrique n'a pas été mesurée (absente de
    `measured_metrics`) n'est pas déclenché — on ne tue pas une stratégie
    sur une donnée manquante, mais le verdict le rend visible
    (`measured_value=None`) plutôt que de le passer sous silence.
    """
    verdicts = []
    for criterion in hypothesis.kill_criteria:
        value = measured_metrics.get(criterion.metric)
        if value is None:
            triggered = False
        elif criterion.comparison == "less_than":
            triggered = value < criterion.threshold
        else:
            triggered = value > criterion.threshold
        verdicts.append(
            KillCriterionVerdict(criterion=criterion, measured_value=value, triggered=triggered)
        )
    return KillCriteriaVerdict(strategy_id=hypothesis.strategy_id, criteria=tuple(verdicts))


class StrategyLifecycleRepository:
    """Statut courant de chaque stratégie. `dead` est un piège à sens unique (I1-like)."""

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

    def __enter__(self) -> StrategyLifecycleRepository:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def status(self, strategy_id: str) -> StrategyStatus | None:
        """Statut courant de `strategy_id`, ou `None` si jamais enregistrée."""
        row = self._conn.execute(
            "SELECT status FROM strategy_lifecycle WHERE strategy_id = ?", (strategy_id,)
        ).fetchone()
        return None if row is None else StrategyStatus(row["status"])

    def register_hypothesis(self, hypothesis: HypothesisSheet) -> None:
        """Enregistre une nouvelle stratégie en statut `candidate`.

        Si `hypothesis.parent_strategy_id` est renseigné, le parent doit
        exister et être `dead` — une nouvelle fiche ne se rattache qu'à une
        idée effectivement enterrée, jamais à une candidate encore en cours.

        Raises:
            UnknownStrategyError: si `strategy_id` existe déjà.
            DeadParentNotDeadError: si le parent référencé n'est pas `dead`.
        """
        if self.status(hypothesis.strategy_id) is not None:
            raise UnknownStrategyError(
                f"strategy '{hypothesis.strategy_id}' already registered; "
                "use a new strategy_id to retest an idea"
            )
        if hypothesis.parent_strategy_id is not None:
            parent_status = self.status(hypothesis.parent_strategy_id)
            if parent_status is None:
                raise UnknownStrategyError(
                    f"parent strategy '{hypothesis.parent_strategy_id}' not registered"
                )
            if parent_status is not StrategyStatus.DEAD:
                raise DeadParentNotDeadError(
                    f"parent strategy '{hypothesis.parent_strategy_id}' is '{parent_status.value}',"
                    " not 'dead' — only a dead idea can be retested under a new hypothesis"
                )

        self._conn.execute(
            "INSERT INTO strategy_lifecycle VALUES (?, ?, ?, datetime('now'))",
            (hypothesis.strategy_id, StrategyStatus.CANDIDATE.value, hypothesis.parent_strategy_id),
        )
        self._conn.commit()

    def apply_verdict(self, verdict: KillCriteriaVerdict) -> StrategyStatus:
        """Applique un verdict de critères de mort : passe à `dead` si déclenché.

        Idempotent et sans effet si la stratégie est déjà `dead` — jamais de
        retour en arrière, même si le nouveau verdict ne déclenche rien.

        Raises:
            UnknownStrategyError: si `verdict.strategy_id` n'est pas enregistrée.
        """
        current = self.status(verdict.strategy_id)
        if current is None:
            raise UnknownStrategyError(f"strategy '{verdict.strategy_id}' not registered")
        if current is StrategyStatus.DEAD or not verdict.any_triggered:
            return current

        self._conn.execute(
            "UPDATE strategy_lifecycle SET status = ?, updated_at = datetime('now') "
            "WHERE strategy_id = ?",
            (StrategyStatus.DEAD.value, verdict.strategy_id),
        )
        self._conn.commit()
        logger.warning("strategy marked dead id=%s", verdict.strategy_id)
        return StrategyStatus.DEAD

    def lineage(self, strategy_id: str) -> list[str]:
        """Chaîne de filiation de `strategy_id`, du plus ancien ancêtre à lui-même."""
        chain = [strategy_id]
        current = strategy_id
        while True:
            row = self._conn.execute(
                "SELECT parent_strategy_id FROM strategy_lifecycle WHERE strategy_id = ?",
                (current,),
            ).fetchone()
            if row is None or row["parent_strategy_id"] is None:
                break
            current = row["parent_strategy_id"]
            chain.append(current)
        return list(reversed(chain))
