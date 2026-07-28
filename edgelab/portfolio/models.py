"""Modèles du module portefeuille : corrélation, simulation jointe, combinaison (Phase 6)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from edgelab.propsim.models import PropSimResult


class CorrelationMatrix(BaseModel):
    """Matrice de corrélation entre stratégies, carrée et symétrique par construction."""

    model_config = ConfigDict(frozen=True)

    strategy_ids: tuple[str, ...]
    matrix: tuple[tuple[float, ...], ...]

    def correlation(self, strategy_a: str, strategy_b: str) -> float:
        """La corrélation entre deux stratégies nommées.

        Raises:
            KeyError: si l'une des deux stratégies est inconnue de la matrice.
        """
        if strategy_a not in self.strategy_ids or strategy_b not in self.strategy_ids:
            raise KeyError(f"unknown strategy in ({strategy_a!r}, {strategy_b!r})")
        i = self.strategy_ids.index(strategy_a)
        j = self.strategy_ids.index(strategy_b)
        return self.matrix[i][j]


class MarginalContribution(BaseModel):
    """Contribution marginale d'une stratégie au P(passage) du portefeuille.

    `delta` peut être négatif : ajouter une stratégie corrélée et à faible
    edge doit pouvoir dégrader le score du portefeuille plutôt que
    l'améliorer (spec Phase 6) — ce module ne le masque jamais.
    """

    model_config = ConfigDict(frozen=True)

    strategy_id: str
    p_pass_with: float
    p_pass_without: float

    @property
    def delta(self) -> float:
        """Écart de P(passage) attribuable à la présence de cette stratégie dans le portefeuille."""
        return self.p_pass_with - self.p_pass_without


class CombinationResult(BaseModel):
    """Résultat complet de l'explorateur : P(passage), corrélation, contributions marginales."""

    model_config = ConfigDict(frozen=True)

    strategy_ids: tuple[str, ...]
    weights: dict[str, float]
    portfolio: PropSimResult
    correlation: CorrelationMatrix
    marginal_contributions: tuple[MarginalContribution, ...]


class AllocationSearchResult(BaseModel):
    """Meilleure allocation trouvée par recherche aléatoire sur le simplexe des poids.

    Le critère de recherche est toujours P(passage), jamais le Sharpe ni le
    rendement espéré (I5).
    """

    model_config = ConfigDict(frozen=True)

    weights: dict[str, float]
    portfolio: PropSimResult
    n_candidates_evaluated: int
