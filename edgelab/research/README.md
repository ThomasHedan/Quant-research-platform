# edgelab.research

**Rôle.** Event study sans gestion de position : rendement forward par horizon, MAE/MFE, stabilité par sous-période, espérance par tercile de volatilité, décroissance au décalage, règle naïve de contrôle, espérance hors 5 % des meilleurs trades. Sortie à horizon fixe uniquement — jamais de SL/TP (c'est le rôle de `backtest/`, Phase 3).

**Décision de design (agrégation multi-instruments).** Le mode par défaut est un univers, pas un instrument. `run_event_study` combine les t-stats *par instrument* via `aggregate_t_stat = mean(t_i) * sqrt(n_instruments)` (Grinold, IR ≈ IC × √N) plutôt que de regrouper tous les trades de l'univers dans un seul test — c'est ce qui fait qu'un edge à t ≈ 1,5 sur 12 marchés décorrélés agrège vers t ≈ 5, conformément à la spec. Un rapport à un seul instrument (`is_mono_instrument`) porte toujours `width_warning` : un edge qui n'existe que sur un marché est du bruit sélectionné.

**Décision de design (règle naïve de contrôle).** La naïve est une position longue inconditionnelle sur *chaque* barre éligible du même instrument, avec le même modèle de coût et les mêmes horizons — pas une reformulation du déclencheur. `HorizonComparison` porte toujours les deux jeux de statistiques côte à côte, plus un test de Welch (`comparison_p_value`) et un verdict booléen `improves_on_naive`. C'est une simplification volontaire et documentée : une naïve plus sophistiquée (ex. même distribution de direction que le signal) est un raffinement possible d'une phase ultérieure, pas un changement d'invariant.

**Décision de design (concentration).** `ConcentrationStats` (espérance hors le `top_pct_exclude`, 5 % par défaut, des meilleurs trades) est absent (`None`) quand `|t| < CONCENTRATION_MIN_T` (1.0, fixé par la spec) à l'horizon primaire — jamais exprimé en ratio de l'espérance de base, qui exploserait pour un edge indiscernable de zéro.

**Limite connue.** La jointure signal/barres et le coût par instance de trade utilisent une boucle Python (`_PriceSeries`), pas une opération Polars entièrement vectorisée. Correct et suffisant pour la taille d'un event study de recherche (des milliers à basses dizaines de milliers de signaux) ; pas dimensionné pour rejouer un signal sur plusieurs Go de M1 en un seul appel sans optimisation ultérieure.

**Ce module refuse de faire.** Gérer une position (SL/TP, trailing) — c'est `backtest/`. Afficher une conclusion positive quand |t| < seuil de significativité (`EventStudyConfig.significance_t`, 1.96 par défaut). Rapporter la concentration en ratio de l'espérance de base. Comparer un signal à sa règle naïve sans les montrer côte à côte. Agréger l'univers en regroupant les trades bruts plutôt qu'en combinant les t-stats par instrument.

**Statut.** Phase 2 livrée : `EventStudyConfig`, `run_event_study`, tous les diagnostics listés au rôle ci-dessus.
