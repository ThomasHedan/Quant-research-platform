# edgelab.data

**Rôle.** Ingestion (Dukascopy, CSV/Parquet génériques, futures continus), contrôle d'intégrité obligatoire, store des données de marché et lockbox du holdout (I3).

**Décision de design (lockbox).** `HoldoutLockbox.access()` est le seul point d'entrée vers le holdout : il refuse toute raison vide ou composée uniquement d'espaces, journalise chaque accès (stratégie, raison, horodatage) dans une table SQLite append-only — même garde-fou par triggers que le registre d'essais — et renvoie le compteur permanent qui en résulte. `is_flagged()` expose le seuil de trois accès mentionné par I3 pour que l'UI puisse afficher le drapeau rouge sans recalculer la règle elle-même.

**Décision de design (intégrité).** `run_integrity_checks` distingue deux sévérités : `CRITICAL` (`session_gaps`, `duplicate_bars`) déclenche la quarantaine, `WARNING` (`aberrant_ticks`, `zero_volume`, `dst_transitions`, `holiday_anomalies`) figure dans le rapport sans bloquer. Ce n'est pas ce que la spec énumère à plat, mais traiter chaque bascule DST semestrielle comme une quarantaine rendrait l'outil inutile sur toute série de plus de six mois. Le seuil de détection des ticks aberrants est calculé sur un écart-type glissant qui *exclut* le point testé (`shift(1)` avant `rolling_std`) : sinon un pic isolé gonfle son propre écart-type de référence et échappe à la détection.

**Décision de design (futures continus).** `splice_continuous_future` n'a pas de valeur par défaut pour `roll_method` : `RATIO`, `DIFFERENCE` et `NONE` doivent être choisis explicitement à chaque appel. `RATIO`/`DIFFERENCE` back-ajustent l'historique de façon cumulative à chaque roll (méthode Panama) — un contrat plus ancien porte l'ajustement de *tous* les rolls entre lui et le contrat le plus récent, qui sert d'ancre non ajustée.

**Décision de design (Dukascopy).** `parse_bi5` est une fonction pure (bytes -> `DataFrame`), testée sur des flux `.bi5` synthétiques sans jamais toucher au réseau. Le seul point de contact réseau (`fetcher: Fetcher`) est injecté en paramètre, à la frontière du module — le cœur du parsing reste testable en isolation.

**Ce module refuse de faire.** Raccorder des futures sans méthode explicite, laisser un dataset en quarantaine atteindre le backtester, exposer le holdout sans raison écrite tracée, remettre un compteur d'accès à zéro, réécrire silencieusement un dataset déjà stocké (`dataset_id` dupliqué -> erreur), attribuer une conclusion positive à un warning (un dataset avec uniquement des `WARNING` reste `ok`).

**Statut.** Phase 0 (`HoldoutLockbox`, I3) et Phase 1 (ingestion CSV/Parquet/Dukascopy/futures continus, contrôle d'intégrité, manifeste versionné, store DuckDB+Parquet) livrées.
