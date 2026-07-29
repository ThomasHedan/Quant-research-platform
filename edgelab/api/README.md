# edgelab.api

**Rôle.** FastAPI en lecture seule sur les artefacts produits par le CLI, plus quelques déclencheurs de job (et, depuis la Phase 7, d'écriture). Sert le front React (`web/`) : leaderboard, fiche stratégie, surface de risque, explorateur de combinaisons, journal d'essais, bibliothèque de papiers.

**Décision de design (artefacts vs job triggers).** `store.py` lit deux sources d'artefacts réels : le registre SQLite (`edgelab.registry`, I1) et des bundles JSON par stratégie (`seed_data/strategies/*.json`, voir `scripts/seed_demo_strategies.py`). Deux fonctions font exception — `run_correlation`, `run_combination` et `run_risk_surface` (sur un ruleset différent de celui précalculé) — et délèguent entièrement à `edgelab.portfolio` / `edgelab.propsim` : ce sont des « déclencheurs de job » explicitement permis par l'architecture (`CLAUDE.md` §3), pas de la logique métier propre à l'API, puisqu'aucune décision n'y est prise et qu'aucun calcul n'y est dupliqué. Elles existent parce que l'explorateur de combinaisons et le sélecteur de ruleset sont interactifs par nature (spec Phase 8) : leur résultat dépend d'une sélection faite dans l'UI, qu'aucun artefact précalculé ne peut anticiper.

**Décision de design (bundle de stratégie).** Un `StrategyBundle` (`schemas.py`) réexpose directement les modèles de calcul existants (`HypothesisSheet`, `PropSimComparison`, `WalkForwardResult`, ...) plutôt que de les dupliquer dans un schéma HTTP parallèle. Seuls les objets sans foyer naturel dans `edgelab.research/validation/propsim/portfolio` (agrégation par sous-période, par tercile de volatilité, par instrument, fan chart Monte Carlo) sont définis ici.

**Décision de design (rulesets, identifiants).** Les rulesets sont adressés par le nom de leur fichier (`ftmo`, `the5ers`, `fundingpips`, `topstep`), pas par leur nom d'affichage (`PropFirmRuleset.ruleset_name`, ex. « FTMO Challenge (2-Step) ») : le premier est stable et adapté à une URL, le second sert à l'affichage. Les noms de palier ne sont **pas** uniformes d'une firme à l'autre (`challenge` chez FTMO, `combine` chez Topstep, `phase_1` chez The5ers/FundingPips) — `/api/rulesets` les liste explicitement plutôt que de supposer un nom générique, et les endpoints interactifs se rabattent sur le premier palier du ruleset choisi quand `phase` n'est pas fourni.

**Décision de design (module papiers, écriture).** `POST /api/papers`, `POST /api/papers/{id}/hypothesis` et `PATCH /api/papers/{id}/status` étendent le principe des déclencheurs de job à l'écriture : ils marshallent une requête HTTP vers `edgelab.papers.PaperRepository`, qui porte seule la validation — y compris la règle de falsifiabilité I2, réutilisée telle quelle depuis `edgelab.strategies.models.HypothesisSheet` (400 si `where_it_should_not_work` est vide). Rien n'est décidé dans `main.py`/`store.py` ; rien n'écrit dans `edgelab/strategies/` ni ne déclenche de backtest — ce périmètre s'arrête délibérément à un brouillon d'hypothèse « à faire tourner soi-même via le CLI », voir `edgelab/papers/README.md`. `GET /api/papers/prompt` doit être déclaré avant `GET /api/papers/{paper_id}` dans `main.py` : même forme de route, le premier enregistré gagne chez Starlette.

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

**Ce module refuse de faire.** Contenir la moindre logique métier ou calcul statistique qui n'existe pas déjà dans un sous-package `edgelab.*`. Deviner un ruleset ou un palier par défaut plutôt que de lister explicitement ce qui existe. Écrire du code de stratégie ou lancer un backtest depuis un endpoint papiers.

**Statut.** Phase 8 (backend) livré : `schemas.py`, `store.py`, `main.py`, `scripts/seed_demo_strategies.py`. Phase 7 (papiers) livrée : endpoints `/api/papers*` dans `main.py`, marshalling dans `store.py`. Testé (`tests/test_api_store.py`, `tests/test_api_main.py`, `tests/test_cli_api.py`, `tests/test_cli_paper.py`).

**Complément — données de marché.** `/api/datasets`, `/api/datasets/{id}` et `/api/instruments` sont de la lecture pure. `/api/provider/catalog`, `/api/provider/download` et `/api/datasets/holdout` sont des déclencheurs de job au sens de ce README : ils marshallent une requête HTTP vers `edgelab.data` (catalogue LSE, ingestion, lockbox) et n'y ajoutent aucune règle. En particulier, l'API ne réimplémente pas I3 : elle appelle `load_holdout`, qui exige la raison écrite et incrémente le compteur, exactement comme le CLI. Un téléchargement qui finit en quarantaine renvoie **200** avec `quarantined: true` — le dataset a bien été créé et reste consultable pour diagnostic ; c'est le backtester qui le refusera, pas l'API.
