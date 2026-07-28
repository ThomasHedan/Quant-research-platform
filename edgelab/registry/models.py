"""Modèle `Trial` : la ligne que le registre écrit pour chaque essai de recherche (I1)."""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TrialType(enum.StrEnum):
    """Nature de l'exécution de recherche enregistrée dans le registre."""

    EVENT_STUDY = "event_study"
    BACKTEST = "backtest"
    WALK_FORWARD = "walk_forward"
    OPTIMIZATION = "optimization"


class Trial(BaseModel):
    """Un essai de recherche, tel qu'il est écrit — une fois, pour toujours — dans le registre.

    Immuable côté modèle (`frozen=True`) : un essai qui doit être corrigé est un
    nouvel essai, jamais une mutation du précédent. `lineage_hash` combine
    `code_hash`, `params_hash` et `dataset_hash` (voir `registry.hashing`) ;
    deux essais construits sur des entrées identiques partagent le même
    lineage, ce qui permet de repérer une ré-exécution à l'identique.
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    trial_type: TrialType
    strategy_id: str
    code_hash: str
    params: dict[str, Any]
    params_hash: str
    dataset_hash: str
    lineage_hash: str
    metrics: dict[str, float] = Field(default_factory=dict)
    artifacts_path: str | None = None
    note: str = ""
