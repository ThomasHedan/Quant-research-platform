# edgelab-web

Vue en lecture sur les artefacts produits par le CLI Python (`edgelab/api/` sert de pont FastAPI, sans logique métier). Aucun calcul ne doit vivre ici — cf. règle d'architecture dans `CLAUDE.md` §3. L'explorateur de combinaisons et le changement de ruleset sur la surface de risque sont des déclencheurs de job documentés dans `edgelab/api/README.md` : ils délèguent entièrement à `edgelab.portfolio`/`edgelab.propsim`, jamais de calcul dupliqué côté web. La bibliothèque de papiers (Phase 7) étend ce principe à l'écriture (créer une fiche, rattacher un brouillon d'hypothèse, changer un statut de triage) : le JSON collé par l'utilisateur n'est jamais re-validé côté front, c'est `edgelab.papers` (via l'API) qui porte seul la validation.

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

**Rouge** : toujours réservé à `dead` / breach / drapeau holdout (I3), jamais étendu au-delà — mais rendu plus présent à l'intérieur de ce périmètre. La fiche stratégie d'une stratégie morte hérite d'un traitement rouge nettement plus marqué (bordure gauche épaisse, fond teinté) ; le leaderboard et la liste de sélection de l'explorateur de combinaisons portent la même bordure gauche rouge sur une ligne `dead` ; `StatCell` accepte un `tone="destructive"` utilisé pour surligner en rouge une probabilité de breach propsim (`P(breach perte journalière)`, `P(breach DD max)`) quand elle dépasse un seuil matériel (≥ 5 %) — visible sur `edgelab/api/seed_data/strategies/demo_orb_friction_floor.json` (72,5 % de breach DD max, rouge plein) contre une stratégie saine où ces probabilités restent en texte neutre.

**Densité** : la fiche stratégie (`StrategyDetail.tsx`) est passée d'une colonne unique plafonnée à 900px à une disposition en colonnes CSS (`columns-1 xl:columns-2`) sur toute la largeur disponible, chaque section devenant un panneau bordé indépendant — la kill card reste seule, en tête, hors de la grille. Résultat mesuré : hauteur totale de page réduite d'environ 28 % malgré l'ajout des deux nouvelles statistiques de breach. La vue « surface de risque » place désormais les chiffres exacts (stats + tableau complet) à côté du graphique plutôt qu'en dessous, pour tout voir sans défiler.

## Structure

- `src/lib/types.ts` — miroir des schémas Pydantic servis par l'API (snake_case, pas de conversion camelCase).
- `src/lib/api.ts` — client fetch typé, une fonction par endpoint.
- `src/lib/derived.ts` — miroir des `@property` Python non sérialisées par Pydantic (`any_triggered`, `delta`, `edge_contribution_p_pass`, `best_point`, `n_windows`, `correlation()`) : toute vue qui a besoin de l'une de ces valeurs importe la fonction correspondante plutôt que de la recalculer à sa façon.
- `src/components/` — coquille (`AppShell`), élément signature (`KillCard`), primitives d'affichage (`StatCell`, `StatusBadge`, `DataState`), composants shadcn/ui de base sous `ui/`.
- `src/pages/` — les six vues (`Leaderboard`, `StrategyDetail`, `RiskSurfacePage`, `PortfolioExplorer`, `PapersLibrary`, `TrialLog`), routées dans `App.tsx`.
- `src/pages/papers/` — sous-composants de `PapersLibrary` : `PaperIntakeCard` (prompt + insertion JSON pour créer une fiche), `HypothesisIntake`/`HypothesisDraftView` (idem pour le brouillon d'hypothèse, ou son affichage une fois rattaché), `StatusChanger` (triage manuel, `mort` exige un motif), `CopyPromptButton` (presse-papiers).

## Ce que ce module refuse de faire

Recalculer une statistique ou une simulation déjà produite par `edgelab.*` (Python). Afficher une moyenne sans son intervalle de confiance. Utiliser le vert pour "rentable". Coder en dur le texte d'un prompt (source unique : `edgelab.papers.prompts`, servie par l'API). Écrire du code de stratégie exécutable ou déclencher un backtest depuis la bibliothèque de papiers.

## Statut

Phase 8 livrée : les six vues sont branchées sur l'API réelle, vérifiées en exécution (build + lint propres, six routes rendues sans erreur console, mode sombre et clavier vérifiés). Phase 7 (papiers) livrée : flux complet copier-le-prompt -> coller-le-JSON pour la fiche papier et pour le brouillon d'hypothèse, filtres langue/famille/classe d'actifs, tri par testabilité, triage manuel — vérifié en exécution de bout en bout (Playwright, clair/sombre/mobile).
