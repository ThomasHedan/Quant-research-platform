# edgelab-web

Vue en lecture sur les artefacts produits par le CLI Python (`edgelab/api/` sert de pont FastAPI, sans logique métier). Aucun calcul ne doit vivre ici — cf. règle d'architecture dans `CLAUDE.md` §3.

Stack : React + Vite + TypeScript + Tailwind v4 + shadcn/ui (`components.json` configuré, ajouter des composants avec `npx shadcn@latest add <name>`), TanStack Table pour les grilles, Recharts pour les graphiques.

```bash
npm install
npm run dev       # serveur de dev
npm run build     # typecheck (tsc -b) + build
npm run lint      # oxlint
```

Les vues (leaderboard, fiche stratégie, surface de risque, explorateur de combinaisons, bibliothèque de papiers, journal d'essais) sont construites en Phase 8, une fois l'API disponible. La direction visuelle (palette, typographie, kill card) est décidée à ce moment-là — voir `CLAUDE.md` §4 Phase 8.
