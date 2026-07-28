# EdgeLab

Plateforme de recherche quantitative : transformer des papiers de recherche en stratégies validées, ou — beaucoup plus souvent — correctement enterrées.

La spécification complète (invariants, architecture, phases, critères d'acceptation) vit dans [`CLAUDE.md`](./CLAUDE.md) et fait foi. Ne pas dupliquer son contenu ici.

## Démarrage

```bash
uv sync                 # installe les dépendances Python (groupe dev inclus)
uv run pytest           # suite de tests
uv run ruff check .     # lint
uv run mypy edgelab     # typage strict
uv run edgelab --help   # CLI
```

Pour le front (`web/`), voir [`web/README.md`](./web/README.md).

## Structure

```
edgelab/     package Python — toute la logique métier, testable sans serveur
tests/       conftest.py, test_constants.py, test_<module>.py
web/         React + Vite + TypeScript + Tailwind — vue en lecture sur les artefacts
```

Chaque sous-package de `edgelab/` a son propre `README.md` expliquant sa décision de design et ce qu'il refuse de faire.
