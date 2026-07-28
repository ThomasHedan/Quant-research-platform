"""Score de testabilité (Phase 7).

Combine la disponibilité de l'instrument chez les prop firms, l'accessibilité
des données, la mécanisabilité sans discrétion, les coûts déjà intégrés dans
le papier et — le plus important — la quantité de données disponibles
postérieures à la publication (McLean & Pontiff 2016 : une anomalie perd
~26 % de son amplitude hors échantillon et ~58 % après publication ; plus il
existe d'années post-publication à tester, plus le papier est réellement
testable aujourd'hui). C'est pourquoi le protocole impose de tester cette
période en premier, et pourquoi ce facteur compte double dans le score.

Calculé, pas subjectif : aucune pondération n'est ajustable au cas par cas.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from edgelab.papers.models import PaperSheet

POST_PUBLICATION_SATURATION_YEARS = 10.0
"""Au-delà de 10 ans de données post-publication, le facteur plafonne à 1.0."""

POST_PUBLICATION_WEIGHT = 2.0
"""Poids du facteur post-publication — double des trois autres composantes
booléennes et de `costs_considered`, car la spec le désigne explicitement
comme le plus important."""

_COSTS_CONSIDERED_SCORE = {"oui": 1.0, "partiel": 0.5, "non": 0.0}


def post_publication_years(publication_year: int, as_of: date | None = None) -> float:
    """Années écoulées depuis la publication, jamais négatives."""
    reference = as_of or datetime.now(UTC).date()
    return max(0.0, float(reference.year - publication_year))


def compute_testability_score(sheet: PaperSheet, as_of: date | None = None) -> float:
    """Score de testabilité dans [0, 1]. Plus haut = plus testable aujourd'hui.

    `as_of` est injectable pour les tests ; en usage réel, la date du jour
    fait naturellement progresser le score d'un papier au fil du temps, sans
    qu'aucune donnée sur ce papier n'ait changé — c'est le comportement
    voulu, pas un artefact à corriger.
    """
    inputs = sheet.testability_inputs
    boolean_components = (
        1.0 if inputs.instrument_available_at_prop_firms else 0.0,
        1.0 if inputs.data_accessible else 0.0,
        1.0 if inputs.mechanizable_without_discretion else 0.0,
        _COSTS_CONSIDERED_SCORE[sheet.costs_considered.value],
    )
    post_pub_component = min(
        post_publication_years(sheet.publication_year, as_of) / POST_PUBLICATION_SATURATION_YEARS,
        1.0,
    )
    total_weight = len(boolean_components) + POST_PUBLICATION_WEIGHT
    weighted_sum = sum(boolean_components) + POST_PUBLICATION_WEIGHT * post_pub_component
    return weighted_sum / total_weight
