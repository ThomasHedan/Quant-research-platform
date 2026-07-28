# edgelab.validation

**Rôle.** Bootstrap par blocs et iid, test de permutation, Deflated Sharpe Ratio (alimenté par le registre), évaluation des critères de mort. Walk-forward, PBO/CSCV, sensibilité à la date de départ et test de coûts ×2 restent à construire (Phase 4 est livrée partielle, conformément à l'ordre de travail recommandé de `CLAUDE.md` §5).

**Décision de design (bootstrap).** `compare_block_vs_iid_bootstrap` ne calcule pas seulement une moyenne rééchantillonnée : il simule des chemins entiers (par blocs consécutifs, ou trade par trade indépendamment) et mesure des statistiques *de trajectoire* — max drawdown, plus longue série de pertes — sur chacun. C'est la seule façon de faire apparaître l'écart entre les deux méthodes : un scalaire comme la moyenne est invariant au réordonnancement, mais le drawdown et les séries de pertes ne le sont pas. `drawdown_underestimation_ratio` et `streak_underestimation_ratio` sont toujours calculés et exposés, jamais masqués.

**Décision de design (permutation).** Le test opère par retournement de signe (chaque trade a pu tout aussi bien être un gain qu'une perte de même magnitude sous H0), pas par réordonnancement — réordonner une série ne change pas sa moyenne, retourner ses signes si. C'est un test sur le *niveau* du edge ; un test complémentaire (rejouer la stratégie sur un historique de prix permuté) a besoin du moteur de backtest et viendra avec la Phase 3.

**Décision de design (DSR).** `deflated_sharpe_ratio` est le calcul pur, testable en isolation avec n'importe quel `n_trials`. `deflated_sharpe_ratio_from_registry` est le point d'entrée à utiliser en pratique : il lit `n_trials` via `len(TrialRepository.list_trials())`, jamais un entier saisi à la main — l'API ne laisse aucun autre chemin pour alimenter un rapport.

**Décision de design (critères de mort).** `StrategyLifecycleRepository` applique le même garde-fou SQL que le registre d'essais (I1) et la lockbox (I3) : un trigger `BEFORE UPDATE` bloque toute transition `dead -> candidate`, y compris en SQL brut via une connexion séparée. Retester une idée après sa mort exige une nouvelle `HypothesisSheet` (nouveau `strategy_id`), et `register_hypothesis` refuse tout `parent_strategy_id` qui ne pointe pas vers une stratégie effectivement `dead` — la filiation reste interrogeable via `lineage()`.

**Limite connue.** « Sur des données non utilisées », pour le nouvel essai qui reteste une stratégie morte, n'est pas encore vérifié automatiquement contre les datasets déjà consommés par les essais du parent — ce recoupement avec `data/manifest.py` est un travail futur, pas un oubli silencieux.

**Ce module refuse de faire.** Alimenter le DSR avec un nombre d'essais saisi à la main. Ressusciter une stratégie marquée `dead`, même via un verdict sain ultérieur ou une requête SQL directe. Masquer le ratio de sous-estimation bootstrap. Rapporter un test de permutation basé sur un réordonnancement qui ne peut pas changer la moyenne testée.

**Statut.** Phase 4 partielle livrée : `bootstrap.py`, `permutation.py`, `dsr.py`, `kill_criteria.py` (et `edgelab.strategies.models.HypothesisSheet`, I2, dont ce module dépend).
