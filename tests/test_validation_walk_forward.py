"""Tests de edgelab.validation.walk_forward (Phase 4)."""

import numpy as np
import pytest
from edgelab.validation.walk_forward import walk_forward


def test_walk_forward_rejects_empty_returns_by_param() -> None:
    """Il n'y a rien à optimiser sans aucun paramètre candidat."""
    with pytest.raises(ValueError, match="returns_by_param"):
        walk_forward({}, in_sample_size=10, out_of_sample_size=5)


def test_walk_forward_rejects_mismatched_series_lengths() -> None:
    """Toutes les séries de paramètres doivent couvrir la même période."""
    with pytest.raises(ValueError, match="same length"):
        walk_forward({"a": np.zeros(10), "b": np.zeros(20)}, in_sample_size=5, out_of_sample_size=2)


@pytest.mark.parametrize(("in_sample_size", "out_of_sample_size"), [(0, 5), (5, 0), (-1, 5)])
def test_walk_forward_rejects_non_positive_window_sizes(
    in_sample_size: int, out_of_sample_size: int
) -> None:
    """Les tailles de fenêtre doivent être strictement positives."""
    with pytest.raises(ValueError):
        walk_forward(
            {"a": np.zeros(10)},
            in_sample_size=in_sample_size,
            out_of_sample_size=out_of_sample_size,
        )


def test_walk_forward_rejects_non_positive_step() -> None:
    """Un `step` explicite doit lui aussi être strictement positif."""
    with pytest.raises(ValueError, match="step"):
        walk_forward({"a": np.zeros(30)}, in_sample_size=5, out_of_sample_size=5, step=0)


def test_walk_forward_rejects_windows_that_do_not_fit() -> None:
    """Aucune fenêtre ne tient si l'échantillon total dépasse la série disponible."""
    with pytest.raises(ValueError, match="no walk-forward window"):
        walk_forward({"a": np.zeros(10)}, in_sample_size=8, out_of_sample_size=8)


def test_walk_forward_recovers_a_dominant_true_edge_out_of_sample() -> None:
    """Un paramètre nettement supérieur à tous les autres est sélectionné et confirmé en OOS."""
    rng = np.random.default_rng(0)
    n = 400
    returns_by_param = {
        "true": rng.normal(0.5, 1.0, n),
        **{f"noise_{i}": rng.normal(0.0, 1.0, n) for i in range(9)},
    }

    result = walk_forward(returns_by_param, in_sample_size=40, out_of_sample_size=20)

    selected_counts = {p: [w.selected_param for w in result.windows].count(p) for p in {"true"}}
    assert selected_counts["true"] >= result.n_windows * 0.7
    assert result.out_of_sample_mean_return == pytest.approx(0.5, abs=0.3)


def test_walk_forward_on_pure_noise_does_not_transfer_out_of_sample() -> None:
    """Sur du bruit pur, le gagnant en échantillon n'a pas d'edge hors échantillon."""
    rng = np.random.default_rng(1)
    n = 400
    returns_by_param = {f"noise_{i}": rng.normal(0.0, 1.0, n) for i in range(10)}

    result = walk_forward(returns_by_param, in_sample_size=40, out_of_sample_size=20)

    assert abs(result.out_of_sample_mean_return) < 0.3


def test_walk_forward_default_step_is_out_of_sample_size() -> None:
    """Sans `step` explicite, les fenêtres hors échantillon sont contiguës et sans chevauchement."""
    result = walk_forward(
        {"a": np.arange(30, dtype=float)}, in_sample_size=10, out_of_sample_size=10
    )

    assert [w.window_index for w in result.windows] == [0, 1]
