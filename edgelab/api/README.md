# edgelab.api

**Rôle.** FastAPI en lecture seule sur les artefacts produits par le CLI, plus quelques déclencheurs de job. Sert le front React (`web/`) : leaderboard, fiche stratégie, surface de risque, explorateur de combinaisons, journal d'essais, statut du module papiers.

**Décision de design (artefacts vs job triggers).** `store.py` lit deux sources d'artefacts réels : le registre SQLite (`edgelab.registry`, I1) et des bundles JSON par stratégie (`seed_data/strategies/*.json`, voir `scripts/seed_demo_strategies.py`). Deux fonctions font exception — `run_correlation`, `run_combination` et `run_risk_surface` (sur un ruleset différent de celui précalculé) — et délèguent entièrement à `edgelab.portfolio` / `edgelab.propsim` : ce sont des « déclencheurs de job » explicitement permis par l'architecture (`CLAUDE.md` §3), pas de la logique métier propre à l'API, puisqu'aucune décision n'y est prise et qu'aucun calcul n'y est dupliqué. Elles existent parce que l'explorateur de combinaisons et le sélecteur de ruleset sont interactifs par nature (spec Phase 8) : leur résultat dépend d'une sélection faite dans l'UI, qu'aucun artefact précalculé ne peut anticiper.

**Décision de design (bundle de stratégie).** Un `StrategyBundle` (`schemas.py`) réexpose directement les modèles de calcul existants (`HypothesisSheet`, `PropSimComparison`, `WalkForwardResult`, ...) plutôt que de les dupliquer dans un schéma HTTP parallèle. Seuls les objets sans foyer naturel dans `edgelab.research/validation/propsim/portfolio` (agrégation par sous-période, par tercile de volatilité, par instrument, fan chart Monte Carlo) sont définis ici.

**Décision de design (rulesets, identifiants).** Les rulesets sont adressés par le nom de leur fichier (`ftmo`, `the5ers`, `fundingpips`, `topstep`), pas par leur nom d'affichage (`PropFirmRuleset.ruleset_name`, ex. « FTMO Challenge (2-Step) ») : le premier est stable et adapté à une URL, le second sert à l'affichage. Les noms de palier ne sont **pas** uniformes d'une firme à l'autre (`challenge` chez FTMO, `combine` chez Topstep, `phase_1` chez The5ers/FundingPips) — `/api/rulesets` les liste explicitement plutôt que de supposer un nom générique, et les endpoints interactifs se rabattent sur le premier palier du ruleset choisi quand `phase` n'est pas fourni.

**Décision de design (module papiers).** `/api/papers` renvoie `implemented: false` avec un message explicite. La Phase 7 n'est pas livrée : l'API le dit, elle ne renvoie jamais une liste vide qui laisserait croire à une bibliothèque simplement inoccupée.

**Données de démonstration.** `edgelab/api/seed_data/strategies/*.json` est committé, généré par `scripts/seed_demo_strategies.py`. Ce ne sont **pas** des résultats de recherche réels : quatre stratégies synthétiques honnêtement labellisées (`[DÉMO SYNTHÉTIQUE]` dans `economic_hypothesis`), trois mortes reproduisant le motif documenté dans `CLAUDE.md` §1 (ORB sous le plafond de friction, or intraday indiscernable du bruit, volume brut à t-stat nul) et une qui survit (edge injecté connu), chacune passée par les vrais modules `edgelab.validation` / `edgelab.propsim` / `edgelab.portfolio` — jamais des chiffres inventés à la main. Régénérer :

```bash
rm -rf .edgelab edgelab/api/seed_data
uv run python scripts/seed_demo_strategies.py
```

Le script est déterministe (graines dérivées de SHA-256, pas de `hash()` intégré à Python — randomisé par processus) : deux exécutions produisent des fichiers identiques.

**Lancer l'API.**

```bash
uv run edgelab api serve            # http://127.0.0.1:8000
uv run edgelab api serve --reload   # rechargement à chaud, développement
```

**Ce module refuse de faire.** Contenir la moindre logique métier ou calcul statistique qui n'existe pas déjà dans un sous-package `edgelab.*`. Deviner un ruleset ou un palier par défaut plutôt que de lister explicitement ce qui existe. Masquer que la Phase 7 (papiers) n'est pas livrée.

**Statut.** Phase 8 (backend) livré : `schemas.py`, `store.py`, `main.py`, `scripts/seed_demo_strategies.py`. Testé (`tests/test_api_store.py`, `tests/test_api_main.py`, `tests/test_cli_api.py`).
