# edgelab.universe

**Rôle.** Définition d'univers multi-instruments : calendrier de session et modèle de coût par instrument. Livre `fx_majors`, `index_futures`, `energy_metals` et `broad_12` (union des trois, 12 instruments).

**Décision de design.** `SessionCalendar` définit les horaires de session en heure *locale* de la place de cotation (`zoneinfo`), pas en UTC : c'est ce qui permet à `expected_bar_starts` de suivre les changements d'heure (DST) sans callback spécial — chaque jour de calendrier local se convertit en bornes UTC qui glissent d'elles-mêmes de +/-1h aux dates de bascule.

**Avertissement de calibration.** Les spreads, commissions et slippages des instruments livrés dans `universe.py` sont des valeurs illustratives, plausibles et délibérément plutôt pessimistes — pas des cotations vérifiées. Elles sont un point de départ à recalibrer contre un relevé broker/vendeur réel avant tout backtest dont la conclusion compterait (voir CLAUDE.md §7). Les calendriers de session simplifient aussi les horaires réels : FX est modélisé en semaine continue UTC sans la coupure de rollover quotidienne, les futures CME de façon analogue en heure locale `America/Chicago` sans la pause de maintenance quotidienne.

**Ce module refuse de faire.** Fournir un instrument sans modèle de coût attaché, laisser un univers contenir deux instruments du même symbole.

**Statut.** Phase 1 livrée : `SessionCalendar`, `Instrument`, `Universe`, et les quatre univers requis.
