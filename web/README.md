# edgelab-web

Vue en lecture sur les artefacts produits par le CLI Python (`edgelab/api/` sert de pont FastAPI, sans logique métier). Aucun calcul ne doit vivre ici — cf. règle d'architecture dans `CLAUDE.md` §3. Les deux exceptions (explorateur de combinaisons, changement de ruleset sur la surface de risque) sont des déclencheurs de job documentés dans `edgelab/api/README.md` : ils délèguent entièrement à `edgelab.portfolio`/`edgelab.propsim`, jamais de calcul dupliqué côté web.

Stack : React 19 + Vite + TypeScript + Tailwind v4 + shadcn/ui (style "new-york", `components.json` configuré, ajouter des composants avec `npx shadcn@latest add <name>`), TanStack Table pour les grilles, Recharts pour les graphiques, react-router-dom pour le routage.

```bash
npm install
npm run dev       # serveur de dev (http://localhost:5173)
npm run build     # typecheck (tsc -b) + build
npm run lint      # oxlint
```

Nécessite l'API en cours d'exécution (`uv run edgelab api serve`, voir `edgelab/api/README.md`) et des stratégies de démonstration seedées (`uv run python scripts/seed_demo_strategies.py` depuis la racine) — sans quoi les vues affichent honnêtement des états vides plutôt que des données inventées. `VITE_API_BASE` (défaut `http://127.0.0.1:8000`) se configure dans `.env.local`.

## Direction visuelle

« Cadran d'instrument de laboratoire », pas un terminal de trading ni un dashboard SaaS — écarte délibérément les trois réflexes proscrits par `CLAUDE.md` §4 (fond crème + serif + terracotta ; quasi-noir + accent vert acide ; broadsheet à filets fins). Graphite quasi-noir par défaut (demande explicite : UI "plutôt de couleur noire"), grotesk sans-serif, chasse fixe (`tabular-nums`) sur tout nombre. Une seule couleur de signal — un azur électrique, pas un ambre — réservée strictement à la significativité statistique ; jamais de vert "profitable". L'azur plutôt que l'ambre est un choix délibéré : noir + ambre lirait comme un terminal Bloomberg, exactement ce que la spec proscrit ("pas un terminal de trading"). Le rouge reste réservé à l'état `dead` et au drapeau holdout (I3). Angles vifs, filets fins, aucune ombre portée — la profondeur vient du contraste des panneaux, pas d'un drop-shadow. Le mode clair est un repli explicite (`prefers-color-scheme: light` ou `data-theme="light"`), pas le défaut. Tokens dans `src/index.css`.

Un vrai bug d'accessibilité a été trouvé et corrigé pendant ce retravail : l'anneau de focus clavier des liens de navigation était invisible, rogné par le `overflow-x-auto` du header (les liens touchaient les bords haut/bas du conteneur défilant, ne laissant aucune marge pour peindre l'anneau — un clipping d'outline connu de Chromium). Corrigé en donnant au conteneur sa propre marge verticale (`py-3.5`) au lieu d'étirer les liens en hauteur pleine ; vérifié en lisant `getComputedStyle` après le règlement de la transition CSS et par capture d'écran zoomée (`AppShell.tsx`).

## Structure

- `src/lib/types.ts` — miroir des schémas Pydantic servis par l'API (snake_case, pas de conversion camelCase).
- `src/lib/api.ts` — client fetch typé, une fonction par endpoint.
- `src/lib/derived.ts` — miroir des `@property` Python non sérialisées par Pydantic (`any_triggered`, `delta`, `edge_contribution_p_pass`, `best_point`, `n_windows`, `correlation()`) : toute vue qui a besoin de l'une de ces valeurs importe la fonction correspondante plutôt que de la recalculer à sa façon.
- `src/components/` — coquille (`AppShell`), élément signature (`KillCard`), primitives d'affichage (`StatCell`, `StatusBadge`, `DataState`), composants shadcn/ui de base sous `ui/`.
- `src/pages/` — les six vues (`Leaderboard`, `StrategyDetail`, `RiskSurfacePage`, `PortfolioExplorer`, `PapersLibrary`, `TrialLog`), routées dans `App.tsx`.

## Ce que ce module refuse de faire

Recalculer une statistique ou une simulation déjà produite par `edgelab.*` (Python). Afficher une moyenne sans son intervalle de confiance. Utiliser le vert pour "rentable". Masquer qu'une vue (papiers, Phase 7) n'est pas construite derrière un état vide silencieux.

## Statut

Phase 8 livrée : les six vues sont branchées sur l'API réelle, vérifiées en exécution (build + lint propres, six routes rendues sans erreur console, mode sombre et clavier vérifiés).
