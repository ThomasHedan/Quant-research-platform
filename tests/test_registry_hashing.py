"""Tests de edgelab.registry.hashing (I1)."""

from pathlib import Path

from edgelab.registry.hashing import (
    compute_lineage_hash,
    hash_bytes,
    hash_file,
    hash_params,
)

from tests.test_constants import SAMPLE_DATASET_HASH, SAMPLE_PARAMS, SAMPLE_STRATEGY_CODE


def test_hash_bytes_is_deterministic() -> None:
    """Le même contenu produit toujours le même hash."""
    assert hash_bytes(b"abc") == hash_bytes(b"abc")


def test_hash_bytes_changes_with_content() -> None:
    """Un contenu différent produit un hash différent."""
    assert hash_bytes(b"abc") != hash_bytes(b"abd")


def test_hash_file_reads_file_content(tmp_path: Path) -> None:
    """`hash_file` hash le contenu du fichier, pas son chemin."""
    strategy_file = tmp_path / "strategy.py"
    strategy_file.write_bytes(SAMPLE_STRATEGY_CODE)

    assert hash_file(strategy_file) == hash_bytes(SAMPLE_STRATEGY_CODE)


def test_hash_params_ignores_key_order() -> None:
    """L'ordre d'insertion des clés ne doit pas changer le hash."""
    a = {"horizon": 10, "threshold": 0.5}
    b = {"threshold": 0.5, "horizon": 10}

    assert hash_params(a) == hash_params(b)


def test_hash_params_changes_with_value() -> None:
    """Une valeur différente change le hash des paramètres."""
    assert hash_params({"horizon": 10}) != hash_params({"horizon": 11})


def test_lineage_hash_is_deterministic_for_identical_runs() -> None:
    """Critère d'acceptation Phase 0 : deux essais identiques produisent le même lineage."""
    code_hash = hash_bytes(SAMPLE_STRATEGY_CODE)
    params_hash = hash_params(SAMPLE_PARAMS)

    first_run = compute_lineage_hash(
        code_hash=code_hash, params_hash=params_hash, dataset_hash=SAMPLE_DATASET_HASH
    )
    second_run = compute_lineage_hash(
        code_hash=code_hash, params_hash=params_hash, dataset_hash=SAMPLE_DATASET_HASH
    )

    assert first_run == second_run


def test_lineage_hash_changes_with_one_byte_of_strategy_code(tmp_path: Path) -> None:
    """Critère d'acceptation Phase 0 : un octet changé dans le code change le lineage."""
    original_file = tmp_path / "strategy.py"
    original_file.write_bytes(SAMPLE_STRATEGY_CODE)
    mutated_file = tmp_path / "strategy_mutated.py"
    mutated_file.write_bytes(SAMPLE_STRATEGY_CODE[:-1] + b"X")

    params_hash = hash_params(SAMPLE_PARAMS)
    original_lineage = compute_lineage_hash(
        code_hash=hash_file(original_file),
        params_hash=params_hash,
        dataset_hash=SAMPLE_DATASET_HASH,
    )
    mutated_lineage = compute_lineage_hash(
        code_hash=hash_file(mutated_file),
        params_hash=params_hash,
        dataset_hash=SAMPLE_DATASET_HASH,
    )

    assert original_lineage != mutated_lineage


def test_lineage_hash_changes_with_params() -> None:
    """Changer les paramètres change le lineage, à code et dataset identiques."""
    code_hash = hash_bytes(SAMPLE_STRATEGY_CODE)

    lineage_a = compute_lineage_hash(
        code_hash=code_hash,
        params_hash=hash_params({"horizon": 10}),
        dataset_hash=SAMPLE_DATASET_HASH,
    )
    lineage_b = compute_lineage_hash(
        code_hash=code_hash,
        params_hash=hash_params({"horizon": 20}),
        dataset_hash=SAMPLE_DATASET_HASH,
    )

    assert lineage_a != lineage_b
