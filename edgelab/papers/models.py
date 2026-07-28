"""Fiche papier et brouillon d'hypothèse (Phase 7).

L'extraction PDF -> fiche structurée n'est pas construite dans ce premier
jet : elle est déléguée à une IA généraliste via un prompt copiable
(`edgelab.papers.prompts`), et l'utilisateur colle le JSON renvoyé dans
l'UI. `PaperAnalysisRequest` et `HypothesisDraftRequest` sont le contrat
exact de ce JSON — la même forme que le CLI (`edgelab paper add`) et l'API
HTTP valident, pour ne jamais dupliquer la règle entre les deux entrées.

Ce module ne redistribue jamais le texte intégral d'un papier : seuls des
champs de métadonnées courts et des notes personnelles sont stockés, comme
l'exige la spec (CLAUDE.md §4, Phase 7).
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from edgelab.strategies.models import HypothesisSheet

_CURRENT_YEAR_UPPER_BOUND_SLACK = 1
"""Un papier peut être daté de l'année prochaine (preprint en avance de publication)."""

_MIN_LANGUAGE_CODE_LENGTH = 2
"""ISO 639-1 : deux lettres minimum (ex: 'zh', 'fr')."""

_EARLIEST_PLAUSIBLE_PUBLICATION_YEAR = 1900


class TriageStatus(enum.StrEnum):
    """État d'un papier dans la file de triage (spec Phase 7, vue 5)."""

    A_LIRE = "a_lire"
    FICHE_FAITE = "fiche_faite"
    HYPOTHESE_ECRITE = "hypothese_ecrite"
    EN_TEST = "en_test"
    MORT = "mort"
    VALIDE = "valide"


class CostsConsidered(enum.StrEnum):
    """Le papier a-t-il déjà intégré des coûts de transaction réalistes ?"""

    OUI = "oui"
    NON = "non"
    PARTIEL = "partiel"


class ReplicationDifficulty(enum.StrEnum):
    """Difficulté de réplication estimée, telle qu'évaluée par l'IA d'extraction."""

    FAIBLE = "faible"
    MOYENNE = "moyenne"
    ELEVEE = "elevee"


class TestabilityInputs(BaseModel):
    """Entrées booléennes du score de testabilité, évaluées par l'IA d'extraction.

    Ce sont des estimations à vérifier par l'utilisateur, pas des faits
    mesurés par EdgeLab — le score qui en dérive (`papers.testability`)
    hérite de cette incertitude et ne doit jamais être présenté comme plus
    précis qu'il ne l'est.
    """

    model_config = ConfigDict(frozen=True)

    instrument_available_at_prop_firms: bool
    data_accessible: bool
    mechanizable_without_discretion: bool


class PaperAnalysisRequest(BaseModel):
    """Contrat exact du JSON attendu du prompt « Analyse de papier de recherche ».

    Volontairement séparé de `PaperSheet` : ce que l'IA externe peut
    raisonnablement fournir (métadonnées, hypothèse, estimations) exclut les
    champs gérés par EdgeLab lui-même (`id`, `created_at`).
    """

    title: str
    authors: tuple[str, ...]
    publication_year: int
    language_source: str
    venue: str
    anomaly_family: str
    asset_class: str
    frequency: str
    sample_period: str
    claimed_sharpe_or_hit_rate: str
    costs_considered: CostsConsidered
    economic_hypothesis: str
    data_needed: str
    replication_difficulty: ReplicationDifficulty
    instrument_available_at_prop_firms: bool
    data_accessible: bool
    mechanizable_without_discretion: bool
    personal_notes: str = ""
    source_url_or_doi: str = ""

    @model_validator(mode="after")
    def _validate(self) -> PaperAnalysisRequest:
        if not self.title.strip():
            raise ValueError("title must not be empty")
        if not self.authors:
            raise ValueError("authors must not be empty")
        if len(self.language_source.strip()) < _MIN_LANGUAGE_CODE_LENGTH:
            raise ValueError("language_source must be an ISO 639-1-like code (e.g. 'zh', 'fr')")
        if not self.economic_hypothesis.strip():
            raise ValueError("economic_hypothesis must not be empty")
        current_year = datetime.now(UTC).year
        latest = current_year + _CURRENT_YEAR_UPPER_BOUND_SLACK
        if not (_EARLIEST_PLAUSIBLE_PUBLICATION_YEAR <= self.publication_year <= latest):
            raise ValueError(
                f"publication_year must be between {_EARLIEST_PLAUSIBLE_PUBLICATION_YEAR} "
                f"and {latest}"
            )
        return self


class PaperSheet(BaseModel):
    """Fiche papier structurée (Phase 7), telle qu'elle est stockée — un instantané figé.

    Immuable comme `HypothesisSheet` et `Trial` : une correction est une
    nouvelle fiche (nouvel `id`), jamais une mutation silencieuse de la
    précédente.
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    title: str
    authors: tuple[str, ...]
    publication_year: int
    language_source: str
    venue: str
    anomaly_family: str
    asset_class: str
    frequency: str
    sample_period: str
    claimed_sharpe_or_hit_rate: str
    costs_considered: CostsConsidered
    economic_hypothesis: str
    data_needed: str
    replication_difficulty: ReplicationDifficulty
    testability_inputs: TestabilityInputs
    personal_notes: str = ""
    source_url_or_doi: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def from_request(cls, request: PaperAnalysisRequest) -> PaperSheet:
        """Construit la fiche stockée à partir du JSON collé par l'utilisateur."""
        return cls(
            title=request.title,
            authors=request.authors,
            publication_year=request.publication_year,
            language_source=request.language_source,
            venue=request.venue,
            anomaly_family=request.anomaly_family,
            asset_class=request.asset_class,
            frequency=request.frequency,
            sample_period=request.sample_period,
            claimed_sharpe_or_hit_rate=request.claimed_sharpe_or_hit_rate,
            costs_considered=request.costs_considered,
            economic_hypothesis=request.economic_hypothesis,
            data_needed=request.data_needed,
            replication_difficulty=request.replication_difficulty,
            testability_inputs=TestabilityInputs(
                instrument_available_at_prop_firms=request.instrument_available_at_prop_firms,
                data_accessible=request.data_accessible,
                mechanizable_without_discretion=request.mechanizable_without_discretion,
            ),
            personal_notes=request.personal_notes,
            source_url_or_doi=request.source_url_or_doi,
        )


class KillCriterionInput(BaseModel):
    """Un critère de mort tel que fourni par le prompt — sans `recorded_at`.

    `recorded_at` est horodaté par EdgeLab à l'insertion, jamais fourni par
    l'IA externe : la date d'enregistrement d'un critère de mort doit
    refléter le moment réel de pré-enregistrement (I2), pas une date que le
    JSON pourrait falsifier.
    """

    name: str
    metric: str
    comparison: Literal["less_than", "greater_than"]
    threshold: float


class HypothesisDraftRequest(BaseModel):
    """Contrat exact du JSON attendu du prompt « Générer une hypothèse falsifiable »."""

    economic_hypothesis: str
    predicted_direction: Literal["long", "short", "both"]
    predicted_amplitude_atr: float
    predicted_hit_rate: float
    predicted_horizon_bars: int
    where_it_should_not_work: str
    kill_criteria: tuple[KillCriterionInput, ...]
    strategy_code_skeleton: str

    @model_validator(mode="after")
    def _validate(self) -> HypothesisDraftRequest:
        if not self.strategy_code_skeleton.strip():
            raise ValueError("strategy_code_skeleton must not be empty")
        return self


class HypothesisDraft(BaseModel):
    """Brouillon d'hypothèse + squelette de code, rattaché à un papier.

    Délibérément un brouillon : ceci n'écrit rien dans `edgelab/strategies/`
    et ne déclenche aucun backtest. `hypothesis` réutilise
    `edgelab.strategies.models.HypothesisSheet` telle quelle — la règle de
    falsifiabilité (I2, `where_it_should_not_work` non vide) ne doit exister
    qu'à un seul endroit du code. Faire de ce brouillon une stratégie
    testable, gatée par I2 et lançable en backtest, reste une action CLI
    distincte et volontaire (voir `edgelab/strategies/README.md`).
    """

    model_config = ConfigDict(frozen=True)

    paper_id: str
    hypothesis: HypothesisSheet
    strategy_code_skeleton: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
