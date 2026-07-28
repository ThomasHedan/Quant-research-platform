# edgelab.strategies

**Rôle.** Une stratégie = un dossier (spec Pydantic + fiche d'hypothèse + code). `HypothesisSheet` (I2) est le premier morceau livré : elle porte l'hypothèse économique, les prédictions chiffrées, les conditions d'échec et les critères de mort — c'est le contrat que `validation.kill_criteria` évalue en Phase 4.

**Décision de design.** `HypothesisSheet` refuse de se construire si `where_it_should_not_work` est vide : une hypothèse qui ne prédit son échec nulle part n'est pas falsifiable (I2). C'est une validation Pydantic, pas une simple règle de CLI — n'importe quel code qui construit ce modèle hérite du refus, y compris une future commande `edgelab strategy` ou un import en masse.

**Limite connue.** Le gate complet de I2 (« un backtest ne démarre pas sans fiche validée ») n'a pas encore de moteur de backtest à gater — il arrivera avec la Phase 3. Pour l'instant, `HypothesisSheet` est consommée par `validation.kill_criteria` (Phase 4) pour l'évaluation des critères de mort.

**Ce module refuse de faire.** Démarrer un backtest sans fiche d'hypothèse validée contenant des critères de mort (I2, application complète en Phase 3). Accepter une fiche dont la condition d'échec ou la liste de critères de mort est vide.

**Statut.** I2 partiellement livrée avec la Phase 4 : `HypothesisSheet`, `KillCriterion`, `StrategyStatus`.
