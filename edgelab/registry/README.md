# edgelab.registry

**Rôle.** Registre d'essais append-only (I1) : hashing du lineage (code + params + dataset), garde-fou contre UPDATE/DELETE.

**Décision de design.** Le garde-fou contre la mutation est à deux niveaux : `TrialRepository` n'expose aucune méthode `update`/`delete`, et la table SQLite `trials` refuse elle-même toute mutation via des triggers `BEFORE UPDATE`/`BEFORE DELETE` (`RAISE(ABORT, ...)`). Même du code qui contournerait le repository et parlerait à la base directement ne peut pas altérer un essai déjà écrit — l'invariant tient par construction, pas par discipline. Le modèle `Trial` est un `pydantic.BaseModel` gelé (`frozen=True`) : une correction est un nouvel essai, jamais une mutation du précédent.

**Ce module refuse de faire.** Silencer un essai raté, recalculer un hash après coup, exposer une méthode de suppression ou de mise à jour — au niveau Python comme au niveau SQL.

**Statut.** Phase 0 livrée : `Trial`, hashing de lineage (`hashing.py`), `TrialRepository`, commandes CLI `edgelab trial list` / `edgelab trial show <id>`.
