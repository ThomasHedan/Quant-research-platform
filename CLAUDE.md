# EDGELAB — Spécification de construction

À Claude Code : ce fichier est la spécification de référence du projet. Lis-le entièrement avant d'écrire une ligne de code. Ne construis jamais plusieurs phases dans la même session : chaque phase se termine par ses critères d'acceptation, qui doivent être vérifiés et verts avant de passer à la suivante.

Charge et applique les skills `prod-python` et `pytest-test-generator` sur tout le code Python, et `frontend-design` sur la partie web.

## 1. Ce qu'est ce projet

EdgeLab est une plateforme de recherche quantitative dont la fonction est de transformer des papiers de recherche en stratégies validées ou — beaucoup plus souvent — correctement enterrées.

L'utilisateur est un trader/quant en apprentissage qui vise à financer sa recherche via des challenges de prop firms. Il a déjà tué plusieurs idées avec un protocole rigoureux (ORB sous le plafond de friction, or intraday indiscernable du bruit, volume brut à t-stat nul). La plateforme doit industrialiser cette rigueur, pas la contourner.

### Le principe directeur, à respecter dans chaque décision de design

La plateforme est un instrument à tuer des idées, pas à en valider.

Un outil qui rend facile de trouver un backtest flatteur est un outil nuisible. Chaque fois qu'un arbitrage se présente entre « pratique pour l'utilisateur » et « difficile de se mentir à soi-même », choisis le second. Concrètement, cela signifie que certaines actions sont volontairement contraignantes : on ne peut pas lancer un backtest sans avoir pré-enregistré ses critères de mort, on ne peut pas toucher au holdout sans que ce soit tracé, et un essai loggué ne peut pas être supprimé.

### Ce que ce projet n'est PAS

* Pas un bot de trading. Aucune exécution d'ordre réel en phase 0–9.
* Pas un optimiseur. L'optimisation est la dernière étape et la plus encadrée.
* Pas un outil de découverte automatique de signaux. Pas de ML sur données brutes cherchant « ce qui marche ». Toute stratégie part d'une hypothèse économique écrite.

## 2. Les cinq invariants

Ce sont des propriétés que le système doit garantir par construction, pas par discipline de l'utilisateur. Si une phase ultérieure casse un invariant, c'est un bug bloquant.

**I1 — Registre immuable des essais.** Chaque exécution de recherche (event study, backtest, walk-forward, optimisation) écrit une ligne append-only dans le registre, avec un hash du code, des données, des paramètres et de la spec. Aucune suppression, aucune modification. Un essai raté reste visible. Raison : le nombre total d'essais est l'entrée obligatoire du Deflated Sharpe Ratio. Sans registre honnête, toutes les statistiques de significativité de la plateforme sont fausses.

**I2 — Pré-enregistrement obligatoire.** Un backtest ne démarre pas si la stratégie n'a pas de fiche d'hypothèse validée contenant : hypothèse économique en une phrase, prédictions chiffrées avant mesure (direction, amplitude en ATR, hit rate attendu, horizon), les conditions où l'effet doit disparaître, et la liste datée des critères de mort. Le champ « où ça ne doit PAS marcher » est obligatoire et non vide. Une hypothèse qui ne prédit son échec nulle part n'est pas falsifiable et le CLI doit la refuser.

**I3 — Lockbox du holdout.** Les données sont partitionnées en `research` / `validation` / `holdout` à la création du dataset. Le holdout est accessible via un chemin de code distinct qui exige une raison écrite et incrémente un compteur d'accès permanent attaché à la stratégie. Le nombre d'accès holdout apparaît dans l'UI à côté de chaque stratégie. Trois accès = drapeau rouge visible.

**I4 — Pas de look-ahead possible par l'API.** L'accès aux données passe par un objet qui ne renvoie jamais de barre postérieure au timestamp courant du moteur. Il n'existe pas d'API publique retournant le DataFrame complet pendant un backtest. Les tests unitaires doivent inclure un test qui échoue si une stratégie tente d'accéder au futur.

**I5 — La fonction objectif est P(passage), pas le Sharpe.** Le classement par défaut de l'UI, l'allocation de portefeuille et le dimensionnement sont pilotés par la sortie de `propsim` : probabilité de passer un challenge donné sans breach. Le Sharpe, le profit factor et le win rate sont affichés comme diagnostics, jamais comme critère de décision. Le win rate n'est jamais la colonne de tri par défaut.

## 3. Architecture

Monorepo, deux ensembles :

```
edgelab/
├── pyproject.toml            # uv, ruff, mypy strict, pytest
├── edgelab/                  # package Python
│   ├── registry/             # I1 — registre d'essais, hashing, lineage
│   ├── data/                 # ingestion, nettoyage, store, lockbox (I3)
│   ├── universe/             # définition d'univers multi-instruments
│   ├── costs/                # modèle de coûts (spread, commission, slippage)
│   ├── research/             # event study, MAE/MFE, stabilité, régimes
│   ├── backtest/             # moteur event-driven (I4)
│   ├── validation/           # bootstrap, permutation, walk-forward, DSR, PBO
│   ├── propsim/              # simulateur de règles prop firm (I5)
│   ├── portfolio/            # combinaison, corrélation, allocation sous contrainte DD
│   ├── papers/               # ingestion & triage de littérature multilingue
│   ├── export/               # bundle de critique IA
│   ├── strategies/           # une stratégie = un dossier (spec + hypothèse + code)
│   ├── api/                  # FastAPI, lit les artefacts, n'a aucune logique métier
│   └── cli.py                # Typer — l'interface primaire
├── tests/                    # conftest.py, test_constants.py, test_<module>.py
└── web/                      # React + Vite + TS + Tailwind
```

Règle d'architecture non négociable : le CLI est l'interface primaire, l'UI est une vue en lecture (plus quelques déclencheurs de jobs). Toute la logique vit dans le package Python et est testable sans serveur. L'API ne calcule rien : elle lit des artefacts produits par le CLI.

### Stack

* Python 3.12+, `uv` pour l'environnement.
* Polars pour la manipulation de séries (ordre de grandeur : plusieurs Go de barres M1 multi-instruments). Pandas autorisé aux frontières si une lib l'impose.
* DuckDB + Parquet pour le stockage de données de marché et des journaux de trades.
* SQLite pour le registre d'essais et les métadonnées (petit, transactionnel, versionnable).
* Pydantic v2 pour toutes les specs, fiches d'hypothèse et payloads d'API.
* Typer pour le CLI, FastAPI pour l'API.
* NumPy/SciPy/statsmodels pour les statistiques. Pas de `vectorbt`, pas de `backtrader` : le moteur est écrit à la main, c'est un objectif pédagogique du projet.
* Front : React + Vite + TypeScript + Tailwind + shadcn/ui, TanStack Table pour les grilles, visx ou Recharts pour les graphiques.

## 4. Les phases

Chaque phase est un livrable autonome et testé. Ne commence pas la suivante avant que les critères d'acceptation de la précédente soient vérifiés en exécution réelle.

### Phase 0 — Squelette, registre, lockbox

**Livrables**
* Projet initialisé (`uv`, `ruff`, `mypy --strict`, `pytest --cov` configurés dans `pyproject.toml`).
* `registry/` : modèle `Trial` (id, timestamp, type d'essai, `strategy_id`, hash de code, hash de dataset, params, métriques résumées, chemin vers artefacts, note libre). Écriture append-only, garde-fou contre `UPDATE`/`DELETE` au niveau du repository.
* Hashing du lineage : hash du contenu du fichier de stratégie + hash des paramètres + hash du manifeste de dataset. Deux essais identiques doivent produire le même hash.
* `data/lockbox.py` : implémentation de I3.
* CLI : `edgelab trial list`, `edgelab trial show <id>`.

**Critères d'acceptation**
* Un test prouve qu'une tentative de suppression d'essai lève une exception.
* Un test prouve que deux exécutions identiques produisent le même hash de lineage, et qu'un octet changé dans le code de stratégie le change.
* Un test prouve que l'accès au holdout sans raison écrite lève, et qu'avec raison, le compteur s'incrémente et persiste.

### Phase 1 — Données et coûts

**Livrables**
* Ingestion : Dukascopy (tick FX), CSV/Parquet génériques, futures continus avec méthode de raccord explicite (ratio, différence, ou pas de raccord — paramètre obligatoire, pas de défaut silencieux).
* Contrôle d'intégrité obligatoire à l'ingestion, produisant un rapport : trous de session, barres dupliquées, ticks aberrants (déviation en écarts-types glissants), volume nul, DST, jours fériés, changement d'heure de session. Un dataset qui échoue au contrôle est ingéré mais marqué `quarantine` et refusé par le backtester.
* Manifeste de dataset versionné : source, période, fuseau, méthode de raccord, partitionnement research/validation/holdout, hash.
* `costs/` : modèle de coût explicite par instrument — spread (fixe ou modélisé par heure de session), commission, slippage. Le slippage doit dépendre du type d'ordre : un ordre stop intra-barre ne se remplit pas comme une clôture de barre. Fournir au minimum `FixedSpreadCost`, `SessionSpreadCost`, `StressedCost` (multiplicateur ×2 pour le test de robustesse).
* `universe/` : un univers est une liste nommée d'instruments avec leur calendrier de session et leur modèle de coût. Livrer au moins : `fx_majors`, `index_futures`, `energy_metals`, et un univers large `broad_12` couvrant les trois.

**Critères d'acceptation**
* Un dataset avec un trou de session artificiel est détecté et mis en quarantaine.
* Le backtester refuse de démarrer sur un dataset en quarantaine.
* Un test montre que le coût aller-retour d'un trade sur ordre stop est strictement supérieur à celui sur clôture de barre, à instrument identique.

### Phase 2 — Event study (avant tout backtest)

C'est l'étape que la plupart des gens sautent, et c'est pourquoi ils confondent la qualité du signal avec la qualité de leur gestion du risque.

**Livrables**

Un module qui, à partir d'un signal binaire ou continu et sans aucune gestion de position (pas de SL, pas de TP, sortie à horizon fixe), produit :
* Rendement forward par horizon, moyenne, médiane, t-stat, hit rate, net de coûts.
* Distributions MAE / MFE — ce sont elles qui calibreront le SL/TP plus tard, jamais un choix a priori.
* Stabilité par sous-périodes chronologiques.
* Espérance par tercile de volatilité réalisée (pour comprendre, pas pour filtrer : un edge présent dans un seul régime est une hypothèse nouvelle et affaiblie).
* Décroissance au décalage : espérance si l'entrée est décalée de 1, 2, 5, 10 barres. Une décroissance faible signifie que le déclencheur précis n'apporte rien.
* Règle naïve de contrôle, obligatoire : pour chaque signal, exécuter automatiquement une variante de même information sans le déclencheur, et afficher les deux côte à côte. Si le déclencheur n'améliore pas significativement la naïve, le dire explicitement dans le rapport.
* Espérance hors 5 % de meilleurs trades. Métrique bornée et décisive : elle révèle les edges portés par une poignée de trades. Ne jamais rapporter de métrique de concentration exprimée en ratio de l'espérance de base — quand celle-ci est indiscernable de zéro, le dénominateur explose et produit des nombres absurdes. Le module doit taire ces diagnostics quand `|t| < 1`.

Le mode multi-instruments est le mode par défaut. Une event study se lance sur un univers, pas sur un instrument. Le rapport présente d'abord le t-stat agrégé sur l'univers, puis la décomposition par instrument. Rationale : `IR ≈ IC × √N`. Un edge à t = 1,5 sur 12 marchés décorrélés agrège vers t ≈ 5. Un edge qui n'existe que sur un seul instrument de l'univers est du bruit sélectionné, et le rapport doit le signaler comme tel.

**Critères d'acceptation**
* Sur un signal purement aléatoire, le module renvoie un t-stat non significatif et n'affiche aucune conclusion positive.
* Sur un signal synthétique avec edge injecté connu, le module retrouve l'amplitude injectée à moins de 10 %.
* Le rapport d'un signal mono-instrument porte un avertissement explicite de largeur.

### Phase 3 — Moteur de backtest

**Livrables**
* Moteur event-driven, barre par barre, avec I4 garanti par la structure de l'API.
* Modélisation d'ordres : market, limit, stop, avec règles de fill explicites et documentées. Gestion du cas ambigu (barre où le high touche le stop et le low touche le TP) via une politique déclarée, pas un choix implicite favorable.
* Dimensionnement : risque fixe en % du capital, stop en multiple d'ATR, taille de position dérivée. La normalisation par la volatilité doit être le défaut.
* Journal de trades complet : timestamp d'entrée/sortie, prix théorique, prix rempli, coût décomposé, MAE/MFE réalisés, raison de sortie.
* Multi-instruments avec capital partagé et suivi de l'exposition agrégée.

**Critères d'acceptation**
* Un test échoue si une stratégie tente de lire une barre future (I4).
* Une stratégie « buy and hold » reproduit le rendement de l'instrument à moins des coûts, au centime près.
* Une stratégie à espérance nulle par construction produit un PnL net strictement négatif égal aux coûts cumulés.

### Phase 4 — Validation statistique

C'est le cœur scientifique de la plateforme.

**Livrables**
* Bootstrap par blocs (taille 5–20 trades, paramétrable), et bootstrap iid pour comparaison. L'écart entre les deux est l'information utile : l'iid casse la dépendance sérielle et sous-estime les séries de pertes et le drawdown — exactement les variables qui font échouer un challenge. Le rapport affiche systématiquement le ratio de sous-estimation.
* Test de permutation : l'edge survit-il si on mélange les dates ? Rapporte une p-value.
* Walk-forward : optimisation sur fenêtre glissante, évaluation sur la fenêtre suivante uniquement. C'est le seul résultat d'optimisation crédible.
* Deflated Sharpe Ratio (Bailey & López de Prado), alimenté par le nombre réel d'essais lu dans le registre — pas un nombre saisi à la main.
* Probability of Backtest Overfitting (PBO) par CSCV.
* Sensibilité à la date de départ : lancer la stratégie à chacun des 250 premiers jours, rapporter la dispersion des résultats finaux.
* Test de coûts ×2 : un edge qui ne survit pas à deux fois les coûts réalistes est trop fin pour être exploité.
* Évaluation des critères de mort : le module lit la fiche d'hypothèse (I2) et rend un verdict automatique critère par critère. Un critère déclenché marque la stratégie `dead`. Une stratégie `dead` ne peut pas être ressuscitée : pour la retester il faut créer une nouvelle fiche, sur des données non utilisées, et le lien de parenté est conservé et affiché.

**Critères d'acceptation**
* Sur une stratégie construite avec un edge nul, le test de permutation renvoie une p-value uniforme sur [0,1] à travers de multiples graines.
* Le DSR décroît quand on ajoute des essais au registre, à Sharpe constant.
* Un test prouve qu'une stratégie marquée `dead` ne peut pas être remise en `candidate`.

### Phase 5 — propsim

Le simulateur de règles de prop firm. C'est la fonction objectif du projet (I5).

**Livrables**
* Modèle de règles déclaratif en YAML : objectif de profit, perte journalière max, drawdown max (statique ou trailing, sur solde ou sur equity — la distinction est décisive), nombre minimum de jours tradés, durée max, restrictions (news, overnight, week-end, hedging), répartition du profit, règles de phase 2 et de compte financé.
* Livrer les rulesets de FTMO, The5ers, FundingPips, Topstep en fichiers séparés, chacun portant une date de vérification et une URL de source. Un ruleset sans source vérifiée est marqué `unverified` et l'UI l'affiche en évidence — la documentation d'affiliation sur ce sujet est notoirement contradictoire.
* Simulation Monte Carlo prenant en entrée une distribution de trades (issue du bootstrap par blocs, pas iid) et renvoyant : `P(passage)`, `P(breach daily)`, `P(breach max DD)`, temps médian jusqu'à l'objectif, distribution du pire jour.
* Surface de risque : balayage du risque par trade de 0,25 % à 2 %, courbe de P(passage). La courbe est en cloche et son optimum se situe très en dessous du critère de Kelly, car la contrainte de drawdown domine. C'est le résultat le plus important que la plateforme produit et il doit avoir sa propre vue dans l'UI.
* Garde-fou de perte journalière paramétrable (arrêt de la journée à un seuil bien avant la limite), optimisé dans propsim : il coûte du rendement et achète de la probabilité de passage.
* Baseline sans edge, obligatoire et toujours affichée. Pour chaque simulation, calculer aussi P(passage) d'une stratégie à espérance nulle de même profil de variance. La différence entre les deux est le seul chiffre qui mesure la contribution réelle de l'edge. Sans lui, l'utilisateur attribuerait à sa stratégie ce qui n'est qu'un problème de première sortie de barrière. Cette baseline ne peut pas être désactivée dans l'UI.

**Critères d'acceptation**
* Une stratégie à espérance nulle donne P(passage) > 0 et strictement inférieur à celle d'une stratégie à edge positif de variance identique.
* La surface de risque présente bien un maximum intérieur, pas monotone.
* Un ruleset trailing drawdown produit un P(passage) strictement inférieur au même ruleset en drawdown statique, toutes choses égales par ailleurs.

### Phase 6 — Portefeuille et combinaison

**Livrables**
* Matrice de corrélation des rendements par trade et par jour entre stratégies.
* Simulation du daily loss agrégé. Deux stratégies rentables mais corrélées peuvent breacher le même jour. Le propsim de portefeuille ne s'applique jamais aux stratégies isolées.
* Explorateur de combinaisons : sélectionner N stratégies, obtenir P(passage) du portefeuille, la corrélation, la contribution marginale de chaque stratégie, et le portefeuille optimal sous contrainte de drawdown.
* Allocation : poids maximisant P(passage), pas le Sharpe ni le rendement espéré.
* Contribution marginale au P(passage) : ajouter une stratégie doit pouvoir baisser le score du portefeuille, et l'UI doit le montrer clairement.

**Critères d'acceptation**
* Deux stratégies parfaitement corrélées donnent un P(passage) de portefeuille égal à celui d'une seule, à levier ajusté.
* Deux stratégies décorrélées à edge égal donnent un P(passage) strictement supérieur.

### Phase 7 — Module papiers

**Livrables**
* Ingestion de PDF (upload local et par URL). Stocker les métadonnées, les liens et les notes personnelles ; ne pas redistribuer le texte intégral. Les extraits conservés restent courts et servent l'analyse.
* Extraction structurée en fiche papier : titre, auteurs, année de publication, langue, revue/preprint, famille d'anomalie, classe d'actifs, fréquence, période d'échantillon, Sharpe ou hit rate revendiqué, coûts de transaction pris en compte (oui/non/partiel), hypothèse économique en une phrase, données nécessaires, difficulté de réplication.
* Multilingue. Détection de langue automatique ; traitement en anglais, français, allemand, espagnol, italien, portugais, chinois, japonais, russe. La fiche est produite en français quelle que soit la langue source, avec la langue d'origine conservée comme métadonnée et filtrable. Ne pas rejeter un papier non anglophone : la littérature chinoise sur les futures de matières premières et la littérature japonaise sur la microstructure sont sous-exploitées précisément parce qu'elles sont peu lues.
* Score de testabilité calculé, pas subjectif, combinant : instrument disponible chez les prop firms, données accessibles, règles mécanisables sans discrétion, coûts déjà intégrés dans le papier, et — le plus important — quantité de données disponibles postérieures à la date de publication. McLean & Pontiff : une anomalie perd ~26 % de son amplitude hors échantillon et ~58 % après publication. Le module doit donc afficher pour chaque papier la période post-publication testable, et le protocole impose de tester celle-ci en premier.
* File de triage dans l'UI : `à lire` → `fiche faite` → `hypothèse écrite` → `en test` → `mort` / `validé`, avec le motif de mort conservé.

**Critères d'acceptation**
* Un PDF en chinois produit une fiche en français avec `langue_source: zh`.
* Le score de testabilité d'un papier publié en 2023 est strictement inférieur à celui du même papier publié en 2005, toutes choses égales par ailleurs.

### Phase 8 — Interface web

**Vues à livrer**
1. Leaderboard. Grille dense et triable. Colonnes : stratégie, famille, papier source, univers, N trades, espérance nette (bps), t-stat, DSR, PBO, P(passage), delta vs baseline sans edge, max DD p95, pire jour p95, série de pertes max p95, corrélation au portefeuille courant, accès holdout, statut. Tri par défaut : P(passage). Le win rate est présent mais jamais colonne de tri par défaut.
2. Fiche stratégie. Hypothèse et critères de mort en haut (voir « signature » ci-dessous), puis courbe d'equity, distributions MAE/MFE, tableau de stabilité par sous-période, régimes de volatilité, fan chart Monte Carlo, fenêtres de walk-forward, comparaison à la règle naïve de contrôle, décomposition par instrument de l'univers, et le journal complet des essais liés.
3. Surface de risque. Courbe de P(passage) vs risque par trade, avec le point Kelly affiché pour montrer visuellement l'écart. Sélecteur de ruleset.
4. Explorateur de combinaisons. Sélection multiple, matrice de corrélation, P(passage) du portefeuille, contribution marginale.
5. Bibliothèque de papiers. File de triage, filtres par langue / famille / classe d'actifs / score de testabilité.
6. Journal d'essais. Le registre brut, filtrable. Compteur global d'essais bien visible : c'est l'entrée du DSR, l'utilisateur doit le voir monter.

**Direction visuelle**

Le sujet est un instrument de laboratoire, pas un terminal de trading et pas un dashboard SaaS. Écarte trois directions par défaut : le fond crème avec serif contrasté et accent terracotta, le fond quasi-noir avec un accent vert acide, et la mise en page « broadsheet » à filets fins. Ce sont des réflexes, pas des choix.

Contraintes de fond, à respecter quelle que soit la direction retenue :
* Les chiffres sont le contenu principal. Chasse fixe à chiffres tabulaires pour toute donnée numérique, alignement décimal, et une graisse qui rend la comparaison verticale immédiate.
* Une seule couleur de signal, réservée à la significativité statistique. Elle ne sert à rien d'autre. Le vert « profitable » n'existe pas dans cette interface : une stratégie rentable mais non significative ne doit jamais paraître verte.
* L'état `dead` est un état de premier ordre, pas un filtre masqué. Les stratégies mortes restent visibles et lisiblement barrées. Elles sont le produit principal de l'outil.
* L'incertitude est rendue visuellement : intervalles de confiance affichés partout où une moyenne l'est. Un point sans barre d'erreur ne doit pas exister dans cette UI.

**Élément signature : la kill card.** En tête de chaque fiche stratégie, les critères de mort pré-enregistrés sont affichés comme une liste vivante — chacun avec sa valeur seuil, sa valeur mesurée courante, et son état. Les critères déclenchés sont barrés en rouge et la stratégie entière hérite de ce traitement. C'est le premier objet que l'utilisateur voit, avant toute courbe d'equity. Il rappelle à chaque consultation que la question n'est pas « combien ça gagne » mais « qu'est-ce qui la tuerait, et est-ce arrivé ».

Plancher de qualité, sans l'annoncer : responsive, focus clavier visible, `prefers-reduced-motion` respecté.

### Phase 9 — Export pour critique IA

**Livrables**
* Bouton d'export sur la fiche stratégie et sur le portefeuille, produisant un bundle :
  * `report.md` — lisible par un humain et par un LLM, budget de tokens paramétrable (défaut ~15k).
  * `data.json` — toutes les métriques structurées.
  * `trades.csv` — journal complet, optionnel selon la taille.
* Contenu obligatoire du rapport : hypothèse économique et prédictions telles que pré-enregistrées, spec exacte de la stratégie, nombre d'essais menés sur cette stratégie et nombre total d'essais dans le registre, tous les résultats de validation (bootstrap blocs et iid, permutation, walk-forward, DSR, PBO, sensibilité à la date de départ, coûts ×2), sortie propsim avec la baseline sans edge, comparaison au buy & hold sur la même période et le même instrument (rendement, Sharpe, max DD, et le Sharpe différentiel, seul chiffre honnête ici), décomposition par instrument, et le résultat de la règle naïve de contrôle.
* Les résultats négatifs sont inclus par défaut et ne peuvent pas être décochés. Un export qui ne montre que le bon est un outil d'auto-persuasion.
* Un `critique_prompt.md` généré, qui demande explicitement à l'IA destinataire de chercher le biais, de proposer trois raisons pour lesquelles ce résultat pourrait être un artefact, et de nommer le test manquant qui trancherait. Le prompt ne doit pas demander « qu'en penses-tu ? » — cette formulation produit de la complaisance.

**Critères d'acceptation**
* Un export d'une stratégie morte est possible et contient le motif de mort.
* Le bundle respecte le budget de tokens en tronquant les journaux, jamais les statistiques.

## 5. Ordre de travail recommandé

Phases 0 → 2 → 4 (partiel) → 5 avant toute autre chose. Rationale : `propsim` est la fonction objectif ; tant qu'il n'existe pas, ajouter des stratégies ne fait qu'augmenter la surface de data-snooping sans pouvoir décider entre elles.

La phase 3 (backtest complet) peut attendre : l'event study de la phase 2 suffit à tuer la grande majorité des idées, et pour beaucoup moins cher.

La phase 8 (UI) vient tard, mais son squelette peut démarrer dès la fin de la phase 5 pour que le leaderboard existe et donne envie de le remplir.

## 6. Conventions

* Python : appliquer `prod-python`. Type hints partout, syntaxe moderne. Pas de bare `except`. `logging` et non `print`. Docstrings expliquant le pourquoi. Fonctions qui font une chose. Effets de bord aux frontières, cœur pur et testable. `ruff` et `mypy --strict` propres.
* Tests : appliquer `pytest-test-generator`. `conftest.py` avec fixtures et factories, `test_constants.py`, un `test_<module>.py` par module source. pytest pur, jamais unittest. Une docstring d'une ligne par test. AAA visible. Exercer les vraies dépendances in-memory (SQLite `sqlite://`, `tmp_path`) plutôt que de mocker. Couverture branches ≥ 85 %, suite livrée verte.
* Tests spécifiques à ce domaine, obligatoires. Pour tout module statistique, écrire un test sur données synthétiques à propriété connue : bruit pur doit donner un résultat nul, edge injecté doit être retrouvé à l'amplitude injectée. C'est la seule protection contre un backtester subtilement faux qui produit des résultats plausibles — le mode d'échec le plus coûteux de ce projet.
* Commits atomiques par livrable, message décrivant le comportement obtenu.
* Documentation : chaque module a un `README.md` court expliquant la décision de design et ce que le module refuse de faire.

## 7. Ce qui doit te faire t'arrêter et demander

* Une décision qui affaiblirait un des cinq invariants.
* Un choix de modélisation qui rendrait le backtest plus optimiste (politique de fill, hypothèse de coût, gestion des gaps).
* Une règle de prop firm que tu ne peux pas sourcer sur un document officiel.
* Une envie d'ajouter une fonctionnalité qui rendrait plus facile de trouver un beau résultat.

## 8. État du projet

* **Fait** : squelette du monorepo (structure de packages, `pyproject.toml`, tooling `uv`/`ruff`/`mypy`/`pytest`, squelette `web/`).
* **Fait — Phase 0** : `registry/` (modèle `Trial` gelé, hashing de lineage déterministe et sensible à l'octet, `TrialRepository` append-only avec garde-fou SQL en plus du garde-fou Python), `data/lockbox.py` (I3 : raison écrite obligatoire, compteur d'accès permanent, drapeau à 3 accès), commandes CLI `edgelab trial list` / `edgelab trial show <id>`. Les trois critères d'acceptation de la Phase 0 sont couverts par des tests et vérifiés en exécution réelle (`uv run pytest`, `uv run edgelab trial list/show` contre un registre réel). Suite verte, 98,9 % de couverture branches.
* **Fait — Phase 1** : `universe/` (`SessionCalendar` DST-aware via `zoneinfo`, `Instrument`, `Universe`, les quatre univers requis `fx_majors`/`index_futures`/`energy_metals`/`broad_12`), `costs/` (`FixedSpreadCost`, `SessionSpreadCost`, `StressedCost`, slippage par type d'ordre), `data/` (ingestion CSV/Parquet génériques, Dukascopy tick FX avec parsing `.bi5` pur et testé sans réseau, futures continus avec raccord ratio/différence/aucun — paramètre obligatoire, contrôle d'intégrité obligatoire avec sévérité `CRITICAL`/`WARNING` et quarantaine, manifeste de dataset versionné + hash, store DuckDB + Parquet). Les trois critères d'acceptation de la Phase 1 sont couverts par des tests et vérifiés en exécution réelle (trou de session -> quarantaine -> `ensure_backtest_ready` refuse ; coût stop > coût clôture de barre). Suite verte, 117 tests, 98,4 % de couverture branches. Avertissement : les coûts par défaut des univers livrés sont illustratifs (à recalibrer, voir `edgelab/universe/README.md`).
* **Fait — Phase 2** : `research/` (event study sans gestion de position — rendement forward net de coûts par horizon, MAE/MFE, stabilité par sous-période, espérance par tercile de volatilité réalisée, décroissance au décalage 1/2/5/10 barres, règle naïve de contrôle obligatoire côte à côte avec test de Welch, espérance hors 5 % des meilleurs trades tue quand |t| < 1). Mode multi-instruments par défaut : agrégation `aggregate_t_stat = mean(t_i) * sqrt(n_instruments)` (Grinold, IR ≈ IC × √N), rapport mono-instrument porteur d'un avertissement de largeur explicite. Les trois critères d'acceptation de la Phase 2 sont couverts par des tests et vérifiés en exécution réelle (signal aléatoire pur -> t-stat agrégé non significatif ; edge synthétique injecté retrouvé à ~3 % de l'amplitude injectée, sous les 10 % requis ; rapport mono-instrument -> `width_warning` non nul). Suite verte, 155 tests, 98,0 % de couverture branches. Limite documentée : la jointure signal/barres utilise une boucle Python, non vectorisée — suffisant pour un event study de recherche, pas dimensionné pour rejouer un signal sur plusieurs Go de M1 en un seul appel.
* **Fait — Phase 4 (complète)** : `strategies/` (`HypothesisSheet` I2 — hypothèse falsifiable, critères de mort datés, refus de construction si `where_it_should_not_work` est vide). `validation/` : bootstrap par blocs vs iid sur des chemins simulés (max drawdown, plus longue série de pertes) avec ratio de sous-estimation toujours affiché ; test de permutation par retournement de signe ; walk-forward (sélection du paramètre in-sample, performance mesurée uniquement sur la fenêtre suivante jamais vue) ; Probability of Backtest Overfitting par CSCV (Bailey, Borwein, López de Prado & Zhu 2015, découpe symétrique en `n_partitions` blocs) ; Deflated Sharpe Ratio (Bailey & López de Prado) dont `n_trials` est lu dans le registre réel, jamais saisi à la main ; sensibilité à la date de départ (fenêtre de longueur fixe à chaque décalage, pour isoler la dispersion réelle d'un artefact de taille d'échantillon) ; test de coûts ×2 (le coût déjà appliqué une fois est soustrait une seconde fois) ; évaluation des critères de mort avec `StrategyLifecycleRepository` (garde-fou SQL empêchant `dead -> candidate`, même en SQL brut, filiation conservée pour retester une idée morte sous une nouvelle fiche). Les trois critères d'acceptation officiels de la Phase 4 sont couverts par des tests et vérifiés en exécution réelle (test de permutation sous edge nul -> p-values uniformes sur [0,1], test de Kolmogorov-Smirnov p=0,91 ; DSR strictement décroissant de 0,99999845 à 0,78927500 quand n_trials passe de 1 à 10 000, Sharpe constant ; stratégie `dead` confirmée non ressuscitable même par un verdict sain ultérieur). Les modules ajoutés dans ce complément sont eux aussi vérifiés en exécution réelle sur données synthétiques à propriété connue : walk-forward retrouve un edge dominant injecté (moyenne vraie 0,5, OOS mesuré 0,42, sélectionné dans 16/18 fenêtres) et ne transfère pas hors échantillon sur du bruit pur (OOS -0,10) ; PBO = 0,00016 sur un edge réel et stable contre 0,35 sur du bruit pur (mêmes 20 paramètres, 12 870 découpes CSCV) ; sensibilité à la date de départ nettement supérieure sous un régime qui bascule (écart-type 93,8) que sous un régime stable (écart-type 10,8) ; un edge fin (0,0008, coût 0,001) ne survit pas au doublement du coût quand un edge robuste (0,003) y survit. Suite verte, 270 tests, 98,6 % de couverture branches (100 % sur tous les fichiers de `validation/`).
* **Fait — Phase 5** : `propsim/` (I5, fonction objectif du projet). `models.py` (`PropFirmRuleset` déclaratif, `ChallengePhase`, `DailyLossGuard`, `is_verified` portant uniquement sur les paramètres qui alimentent la simulation). `simulator.py` : Monte Carlo par rééchantillonnage de blocs (jamais iid, généralise le principe de `validation.bootstrap` à une longueur de chemin arbitraire), risque par trade recalculé sur le solde courant, drawdown statique (ancré au capital initial) vs trailing (ancré au plus haut solde atteint). `baseline.py` : baseline sans edge par recentrage de moyenne (`zero_edge_returns`), calculée systématiquement à côté de la stratégie, jamais masquable. `risk_surface.py` : balayage du risque par trade et fraction de Kelly continue (E[R]/Var[R]) pour référence. `loader.py` + `rulesets/*.yaml` : quatre rulesets déclaratifs (FTMO, The5ers, FundingPips, Topstep) ; seul FTMO est vérifié (source officielle `ftmo.com/en/trading-objectives/` lue directement, datée) — les trois autres sont livrés `unverified` avec un `note` détaillant précisément quels chiffres sont confirmés vs recoupés (pages officielles The5ers/FundingPips/Topstep bloquées ou incomplètes lors des tentatives de récupération de cette session). Les trois critères d'acceptation de la Phase 5 sont couverts par des tests et vérifiés en exécution réelle : stratégie à espérance nulle -> P(passage) = 0,3996, strictement entre 0 et le P(passage) à edge positif = 0,9280 ; surface de risque en cloche avec maximum intérieur à 1 % de risque par trade (P(passage) = 0,9277), très en dessous de la fraction de Kelly (0,1556) ; ruleset trailing drawdown -> P(passage) = 0,8882 strictement inférieur au même ruleset en statique = 0,9254. Suite verte, 240 tests, 98,5 % de couverture branches (100 % sur tous les fichiers de `propsim/`). Limite documentée : la granularité est le trade clôturé, pas la barre — pas de P&L flottant intrabar, donc `DrawdownBasis.EQUITY` est traité comme `BALANCE` en attendant le moteur de backtest de la Phase 3.
* **Fait — Phase 6** : `portfolio/` (combinaison de stratégies, corrélation, allocation sous contrainte de drawdown). `correlation.py` : matrices de corrélation par trade et par jour (`aggregate_to_daily_returns` agrège par blocs de `trades_per_day`, tronque le reliquat plutôt que de fausser un jour partiel). `simulator.py` : `simulate_portfolio` rééchantillonne toutes les stratégies avec les MÊMES indices de départ de bloc à l'intérieur d'un chemin simulé pour préserver leur corrélation croisée (rééchantillonner indépendamment la détruirait), combine les trajectoires pondérées (`weights` somme à 1, un budget de risque unique partitionné) et réutilise `propsim.simulate_from_paths` — extrait de `propsim/simulator.py` dans ce complément, sans dupliquer la mécanique jour par jour. `combination.py` : `explore_combination` (contribution marginale = P(passage) du portefeuille moins P(passage) sans la stratégie, poids restants renormalisés — peut être négative, jamais masquée) et `optimize_allocation` (recherche aléatoire sur le simplexe des poids par tirages de Dirichlet, critère P(passage) jamais Sharpe ni rendement espéré, I5). Les deux critères d'acceptation de la Phase 6 sont couverts par des tests et vérifiés en exécution réelle : deux stratégies parfaitement corrélées donnent un P(passage) de portefeuille strictement égal à celui d'une seule (0,92025 = 0,92025, budget de risque total identique) ; deux stratégies décorrélées à edge égal donnent un P(passage) strictement supérieur (0,9905 contre 0,96675 en solo). Propriétés additionnelles vérifiées : une stratégie de bruit pur ajoutée au portefeuille a une contribution marginale négative (-0,535) quand la stratégie à edge réel reste positive (+0,414) ; la recherche d'allocation alloue 92 % du budget à la stratégie à edge réel contre 8 % au bruit. Suite verte, 305 tests, 98,8 % de couverture branches (100 % sur tous les fichiers de `portfolio/` et sur `propsim/simulator.py`). Limite documentée : la corrélation par trade et le rééchantillonnage joint supposent le trade `i` de chaque stratégie aligné dans le temps avec le trade `i` des autres, en l'absence d'horodatage réel avant la Phase 3.
* **Fait — Phase 3** : `backtest/` (moteur event-driven, I4 garanti par construction). `market_view.py` : `MarketView.bar_at` n'accepte qu'un décalage relatif `offset <= 0` (positif lève `LookAheadError`), aucune méthode publique ne renvoie le DataFrame complet sous-jacent — une impossibilité structurelle, pas une discipline. `fills.py` : politique de fill déclarée — un ordre marché soumis pendant le traitement de la barre `t` se remplit à l'ouverture de `t+1` (jamais à la clôture de `t`, un look-ahead déguisé) ; un ordre limite/stop se remplit à son niveau ou à l'ouverture si la barre ouvre déjà au-delà (gap), jamais à un prix plus optimiste que le marché ; barre ambiguë (stop et take-profit tous deux dans le range) résolue par « le stop touche en premier » (CLAUDE.md §7). `sizing.py` : risque fixe en % du capital, stop en multiple d'ATR (moyenne mobile simple du vrai range), quantité dérivée — la normalisation par la volatilité est le défaut. `engine.py` : `BacktestEngine` multi-instruments à capital partagé unique (équité = capital initial + PnL réalisé + PnL latent, coût d'entrée défalqué dès le fill), une position ouverte par instrument, séquence par barre non réordonnée (excursions -> sorties bracket -> sorties signal -> entrées -> `strategy.on_bar`), journal de trades complet (MAE/MFE, coûts décomposés par `CostBreakdown`, raison de sortie), exposition agrégée suivie par barre. Les trois critères d'acceptation de la Phase 3 sont couverts par des tests et vérifiés en exécution réelle : une stratégie qui tente de lire une barre future lève `LookAheadError`, propagée par `engine.run` ; un buy-and-hold reproduit le rendement de l'instrument moins les coûts au centime près (diff = 0,0 sur un calcul indépendant du moteur) ; une stratégie à espérance nulle par construction (prix strictement plat) produit un PnL net strictement négatif exactement égal aux coûts cumulés (-600,0 = -600,0 sur 15 trades). Suite verte, 369 tests, 98,96 % de couverture branches (100 % sur tous les fichiers de `backtest/`). Limites documentées : une seule position par instrument à la fois, tous les instruments d'un backtest doivent partager le même calendrier de barres (alignement hétérogène = travail futur), MAE/MFE ne comptabilisent pas la barre d'entrée elle-même.
* **Fait — Phase 8** : `edgelab/api/` (FastAPI en lecture seule) + `web/` (React 19 + Vite + Tailwind v4 + shadcn/ui) livrent les six vues. Backend : `schemas.py` (`StrategyBundle` réexpose directement les modèles de calcul existants plutôt que de les dupliquer), `store.py` (lecture registre + bundles JSON ; `run_correlation`/`run_combination`/`run_optimize_allocation`/`run_risk_surface` sur ruleset non précalculé sont des déclencheurs de job explicitement permis par l'architecture, délèguent entièrement à `edgelab.portfolio`/`edgelab.propsim`, aucun calcul dupliqué), `main.py`. `edgelab api serve` (Typer + uvicorn) garde le CLI comme interface primaire. `scripts/seed_demo_strategies.py` : quatre stratégies de démonstration honnêtement labellisées `[DÉMO SYNTHÉTIQUE]`, passées par les vrais modules `validation`/`propsim`/`portfolio` (jamais de chiffres inventés à la main) — trois mortes reproduisant le motif documenté en §1 (ORB sous le plafond de friction, or intraday indiscernable du bruit, volume brut à t-stat nul), une qui survit (edge injecté connu) ; déterministe (graines SHA-256, jamais `hash()` qui est randomisé par processus) et reproductible bit à bit d'une exécution à l'autre (vérifié). `/api/papers` renvoie `implemented: false` explicitement plutôt qu'une liste vide qui laisserait croire à une bibliothèque simplement inoccupée. Direction visuelle : encre graphite sur gris froid pâle / panneau graphite en sombre, grotesk sans-serif, chasse fixe (`tabular-nums`) sur tout nombre, une seule couleur de signal (ambre) réservée à la significativité statistique, rouge réservé à `dead`/breach — écarte les trois réflexes proscrits en §4. `KillCard` (élément signature, en tête de chaque fiche stratégie, hérite du rouge barré dès qu'un critère est déclenché), intervalle de confiance affiché à chaque moyenne, leaderboard trié par défaut sur P(passage) (win rate jamais colonne de tri par défaut), stratégies `dead` visibles et barrées partout (jamais masquées), drapeau holdout rouge à 3 accès (I3). Vérifié en exécution réelle : les six routes rendent sans erreur console sur des données réelles servies par l'API (Playwright, clair et sombre), navigation clavier et `prefers-reduced-motion` respectés, `npm run build`/`npm run lint` et `ruff`/`mypy --strict`/`pytest` propres. Un bug de performance réel a été trouvé et corrigé en cours de route : `optimize_allocation` appelé depuis l'explorateur de combinaisons prenait ~12 s (30 candidats × 2000 trajectoires) — réduit à ~0,9 s pour un usage interactif (`_N_PATHS_OPTIMIZE`/`_N_CANDIDATES_OPTIMIZE` dans `store.py`), sans toucher aux valeurs utilisées pour les artefacts précalculés. 402 tests, 98,7 % de couverture branches côté Python. Limite documentée : `optimize_allocation` interactif est une approximation moins précise (moins de trajectoires/candidats) que l'exécution CLI de référence, par construction (recherche aléatoire, pas un optimum exact — voir `edgelab/portfolio/README.md`).
* **Fait — retravail visuel de la Phase 8** : demande explicite de l'utilisateur (UI "plutôt de couleur noire" avec une couleur de signal plus pétante). `web/src/index.css` : le graphite quasi-noir devient le thème par défaut (`:root`), le mode clair passe en repli explicite (`data-theme="light"` ou `prefers-color-scheme: light`) au lieu d'être la base. La couleur de signal passe de l'ambre à un azur électrique — délibérément pour éviter qu'un noir + ambre ne lise comme un terminal de trading façon Bloomberg, ce que §4 proscrit explicitement ("pas un terminal de trading"). `AppShell.tsx` retravaillé : filet de bezel signal en tête de page, indicateur de navigation active en soulignement signal, compteur d'essais en pastille avec point pulsé. Un vrai bug d'accessibilité pré-existant a été trouvé et corrigé pendant la vérification : l'anneau de focus clavier des liens de navigation était invisible (rogné par le `overflow-x-auto` du header — les liens en hauteur pleine touchaient les bords du conteneur défilant, laissant zéro marge pour peindre l'outline, un clipping connu de Chromium) ; corrigé en donnant au conteneur sa propre marge verticale plutôt que d'étirer les liens en hauteur pleine, vérifié par lecture de `getComputedStyle` après règlement de la transition CSS et capture d'écran zoomée. Comme les six vues utilisent des tokens sémantiques (`bg-background`, `text-signal`, `var(--color-border)` jusque dans les graphiques Recharts) plutôt que des couleurs codées en dur, le nouveau thème s'est propagé sans toucher aux pages elles-mêmes — seule une relecture visuelle par page a été faite, aucune n'a nécessité de correction de fond. Revérifié en exécution réelle : six routes sans erreur console en clair et en sombre, focus clavier visible (azur) sur desktop et navigation mobile toujours sans retour à la ligne, `npm run build`/`npm run lint` propres.
* **Prochaine session** : Phase 7 — module papiers (le seul morceau qui manque encore à l'ensemble des phases listées en §5), ou approfondissement de l'UI (ex. code-splitting du bundle web, actuellement > 500 kB minifié), selon la priorité choisie par l'utilisateur.
