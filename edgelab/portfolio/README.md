# edgelab.portfolio

**Rôle.** Combinaison de stratégies, corrélation par trade et par jour, allocation sous contrainte de drawdown. Le propsim de portefeuille ne s'applique jamais aux stratégies isolées : deux stratégies rentables mais corrélées peuvent breacher la perte journalière agrégée le même jour, et seule une simulation jointe le révèle.

**Décision de design (corrélation préservée par rééchantillonnage joint).** `simulate_portfolio` rééchantillonne toutes les stratégies avec les MÊMES indices de départ de bloc à l'intérieur d'un même chemin simulé. Rééchantillonner chaque stratégie indépendamment détruirait entièrement leur corrélation croisée — exactement l'information que ce module existe pour préserver. Les trajectoires pondérées sont ensuite combinées en une seule série de rendements agrégés, qui traverse la même mécanique de règles jour par jour que `propsim.simulate_challenge` (via `propsim.simulate_from_paths`, extrait de `propsim/simulator.py` pour ce module plutôt que dupliqué).

**Décision de design (budget de risque unique).** `weights` doit sommer à 1 : les poids partitionnent un seul `risk_per_trade_pct` de portefeuille plutôt que d'en ajouter un par stratégie. Sans cette contrainte, comparer deux allocations reviendrait à comparer des expositions totales différentes, pas des allocations d'un même budget.

**Décision de design (contribution marginale).** `explore_combination` mesure la contribution marginale d'une stratégie comme l'écart de P(passage) entre le portefeuille complet et le même portefeuille sans elle, poids restants renormalisés proportionnellement. Cet écart peut être négatif — une stratégie corrélée et à faible edge doit pouvoir dégrader le portefeuille, ce module ne le masque jamais (voir `test_marginal_contribution_is_negative_for_a_pure_noise_strategy`).

**Décision de design (allocation).** `optimize_allocation` cherche les poids qui maximisent P(passage), jamais le Sharpe ni le rendement espéré (I5), par recherche aléatoire sur le simplexe (tirages de Dirichlet, portefeuille équipondéré toujours inclus comme référence). P(passage) est une sortie Monte Carlo bruitée sans gradient exploitable : une recherche aléatoire structurée est le choix standard pour ce genre de problème, pas une optimisation exacte — ce module ne prétend pas trouver l'optimum global, seulement un candidat qui l'approche sur les candidats évalués.

**Limite connue.** La corrélation par trade et le rééchantillonnage joint supposent que le trade `i` de chaque stratégie est aligné dans le temps avec le trade `i` des autres. C'est une simplification nécessaire tant qu'aucun moteur de backtest (Phase 3) ne produit de trades réellement horodatés ; elle attendra un vrai alignement par timestamp.

**Ce module refuse de faire.** Allouer sur le Sharpe ou le rendement espéré plutôt que sur la contribution au P(passage) du portefeuille. Rééchantillonner les stratégies indépendamment (ce qui détruirait leur corrélation). Masquer une contribution marginale négative.

**Statut.** Phase 6 livrée : `models.py`, `correlation.py`, `simulator.py`, `combination.py`.
