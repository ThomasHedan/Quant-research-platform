"""Walk-forward (Phase 4) — la seule performance d'optimisation crédible.

Une fenêtre glissante choisit son paramètre sur l'échantillon d'entraînement
seul (in-sample), puis mesure la performance de ce choix sur l'échantillon
suivant, jamais vu au moment de la sélection (out-of-sample). Optimiser une
seule fois sur toute la période et rapporter cette même performance mélange
sélection et évaluation — c'est exactement le biais que le walk-forward
élimine par construction.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
from numpy.typing import NDArray

from edgelab.validation.models import WalkForwardResult, WalkForwardWindow


def walk_forward(
    returns_by_param: Mapping[str, NDArray[np.float64]],
    *,
    in_sample_size: int,
    out_of_sample_size: int,
    step: int | None = None,
) -> WalkForwardResult:
    """Walk-forward sur une grille de paramètres, chacun associé à sa série de rendements.

    Le paramètre sélectionné à chaque fenêtre est celui de rendement moyen
    in-sample le plus élevé ; `step` par défaut vaut `out_of_sample_size`
    (fenêtres hors échantillon contiguës, sans chevauchement).

    Raises:
        ValueError: si `returns_by_param` est vide, si les séries n'ont pas
            toutes la même longueur, si `in_sample_size`, `out_of_sample_size`
            ou `step` ne sont pas strictement positifs, ou si aucune fenêtre
            ne tient dans la longueur de série disponible.
    """
    if not returns_by_param:
        raise ValueError("returns_by_param must not be empty")
    lengths = {series.size for series in returns_by_param.values()}
    if len(lengths) != 1:
        raise ValueError("all parameter series must have the same length")
    n = lengths.pop()
    if in_sample_size <= 0 or out_of_sample_size <= 0:
        raise ValueError("in_sample_size and out_of_sample_size must be positive")
    step_size = step if step is not None else out_of_sample_size
    if step_size <= 0:
        raise ValueError("step must be positive")

    windows: list[WalkForwardWindow] = []
    start = 0
    window_index = 0
    while start + in_sample_size + out_of_sample_size <= n:
        in_sample = slice(start, start + in_sample_size)
        out_of_sample = slice(start + in_sample_size, start + in_sample_size + out_of_sample_size)

        best_param = max(
            returns_by_param, key=lambda p: float(np.mean(returns_by_param[p][in_sample]))
        )
        windows.append(
            WalkForwardWindow(
                window_index=window_index,
                selected_param=best_param,
                in_sample_score=float(np.mean(returns_by_param[best_param][in_sample])),
                out_of_sample_return=float(np.mean(returns_by_param[best_param][out_of_sample])),
            )
        )
        start += step_size
        window_index += 1

    if not windows:
        raise ValueError(
            f"no walk-forward window fits: need at least {in_sample_size + out_of_sample_size} "
            f"periods, got {n}"
        )

    oos_returns = np.array([w.out_of_sample_return for w in windows])
    return WalkForwardResult(
        windows=tuple(windows),
        in_sample_size=in_sample_size,
        out_of_sample_size=out_of_sample_size,
        out_of_sample_mean_return=float(np.mean(oos_returns)),
        out_of_sample_total_return=float(np.sum(oos_returns)),
    )
