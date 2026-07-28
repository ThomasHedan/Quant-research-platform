# edgelab.backtest

**Rôle.** Moteur event-driven barre par barre, garantissant l'absence de look-ahead par construction (I4). Modélisation d'ordres market/limit/stop, dimensionnement par risque fixe normalisé par la volatilité (ATR), journal de trades complet (MAE/MFE, coûts décomposés, raison de sortie), multi-instruments à capital partagé.

**Décision de design (I4).** `MarketView.bar_at` n'accepte qu'un décalage relatif `offset <= 0` : positif lève `LookAheadError`. Il n'existe aucune méthode publique retournant le DataFrame complet sous-jacent, ni aucun moyen d'exprimer une demande de barre future à travers l'API — pas seulement une discipline à respecter par la stratégie, une impossibilité structurelle.

**Décision de design (politique de fill).** Un ordre marché soumis pendant le traitement de la barre `t` se remplit à l'ouverture de la barre `t+1`, jamais à la clôture de `t` — la stratégie a vu cette clôture pour décider, elle ne peut pas aussi y être remplie sans look-ahead déguisé. Un ordre limite ou stop se remplit à son niveau, ou à l'ouverture si la barre ouvre déjà au-delà (gap) : jamais à un prix plus optimiste que ce que le marché offrait réellement (voir `fills.py`).

**Décision de design (barre ambiguë).** Quand le stop-loss et le take-profit d'une même position sont tous deux dans le range d'une seule barre, le stop est réputé toucher en premier — hypothèse conservatrice assumée par construction (CLAUDE.md §7), jamais un choix implicite favorable au trade.

**Décision de design (comptabilité).** L'équité est `capital_initial + PnL_réalisé + PnL_latent`, où le PnL latent d'une position ouverte défalque déjà son coût d'entrée (connu et engagé dès le fill), pas seulement à la clôture. Aucune notion de « cash » séparée du capital n'est modélisée : toutes les positions, sur tous les instruments, puisent dans le même solde (capital partagé, spec Phase 3).

**Décision de design (dimensionnement).** `sizing.py` dérive la quantité d'un risque fixe en % du capital et d'une distance de stop en prix — la normalisation par la volatilité (ATR) est le défaut : deux instruments à volatilité différente reçoivent une taille de position différente pour un même risque en capital.

**Limites documentées.**
* Une seule position ouverte par instrument à la fois. Une seconde demande d'entrée sur un instrument déjà positionné est silencieusement ignorée plutôt que mise en file.
* Tous les instruments d'un backtest doivent partager le même calendrier de barres (même nombre de barres, mêmes timestamps) — l'alignement de calendriers hétérogènes (sessions, jours fériés différents) est un travail futur.
* `average_true_range` est une moyenne mobile simple du vrai range, pas le lissage récursif de Wilder — suffisant comme entrée de dimensionnement.
* MAE/MFE ne comptabilisent pas le mouvement de la barre d'entrée elle-même, seulement les barres suivantes tant que la position reste ouverte.

**Ce module refuse de faire.** Exposer une API retournant des barres futures. Résoudre une barre ambiguë (high touche stop, low touche TP) par un choix implicite favorable. Remplir un ordre marché à la clôture de la barre qui a servi à décider.

**Statut.** Phase 3 livrée : `models.py`, `market_view.py`, `fills.py`, `sizing.py`, `engine.py`.
