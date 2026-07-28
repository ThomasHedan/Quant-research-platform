# edgelab.backtest

**Rôle.** Moteur event-driven barre par barre, garantissant l'absence de look-ahead par construction (I4).

**Ce module refuse de faire.** Exposer une API retournant des barres futures, résoudre une barre ambiguë (high touche stop, low touche TP) par un choix implicite favorable.

**Statut.** Squelette — implémentation à venir selon l'ordre de phase défini dans `CLAUDE.md`.
