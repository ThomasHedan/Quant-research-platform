# edgelab.costs

**Rôle.** Modèle de coûts explicite par instrument et par type d'ordre (spread, commission, slippage). Fournit `FixedSpreadCost`, `SessionSpreadCost` (spread par heure UTC) et `StressedCost` (multiplicateur, ×2 par défaut, pour le test de robustesse coûts).

**Décision de design.** Le slippage est paramétré par `SlippageByOrderType` (market/limit/stop) : un ordre marché est traité comme un fill à la clôture de barre (slippage nul par défaut, le prix est connu avant l'action), un ordre stop comme un déclenchement intra-barre (slippage strictement positif par défaut). `SessionSpreadCost` exige un spread pour les 24 heures UTC — une heure manquante lève plutôt que de retomber sur un défaut silencieux.

**Ce module refuse de faire.** Appliquer le même slippage à un ordre stop intra-barre et à une clôture de barre, accepter un spread ou une commission négatifs, laisser `StressedCost` atténuer un coût (`multiplier < 1` refusé).

**Statut.** Phase 1 livrée : `OrderType`, `CostBreakdown`, `CostModel`, `FixedSpreadCost`, `SessionSpreadCost`, `StressedCost`.
