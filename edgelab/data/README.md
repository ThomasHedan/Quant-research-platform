# edgelab.data

**Rôle.** Ingestion, contrôle d'intégrité, store des données de marché et lockbox du holdout (I3).

**Décision de design (lockbox).** `HoldoutLockbox.access()` est le seul point d'entrée vers le holdout : il refuse toute raison vide ou composée uniquement d'espaces, journalise chaque accès (stratégie, raison, horodatage) dans une table SQLite append-only — même garde-fou par triggers que le registre d'essais — et renvoie le compteur permanent qui en résulte. `is_flagged()` expose le seuil de trois accès mentionné par I3 pour que l'UI puisse afficher le drapeau rouge sans recalculer la règle elle-même.

**Ce module refuse de faire.** Raccorder des futures sans méthode explicite, laisser un dataset en quarantaine atteindre le backtester, exposer le holdout sans raison écrite tracée, remettre un compteur d'accès à zéro.

**Statut.** Phase 0 livrée : `HoldoutLockbox` (I3). Ingestion, contrôle d'intégrité et partitionnement research/validation/holdout des datasets : Phase 1.
