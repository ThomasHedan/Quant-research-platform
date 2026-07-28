# edgelab.registry

**Rôle.** Registre d'essais append-only (I1) : hashing du lineage (code + params + dataset), garde-fou contre UPDATE/DELETE.

**Ce module refuse de faire.** Silencer un essai raté, recalculer un hash après coup, exposer une méthode de suppression.

**Statut.** Squelette — implémentation à venir selon l'ordre de phase défini dans `CLAUDE.md`.
