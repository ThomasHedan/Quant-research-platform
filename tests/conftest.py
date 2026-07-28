"""Fixtures et factories partagées entre tous les modules de test.

Convention du projet : exercer les vraies dépendances (SQLite `sqlite://`,
`tmp_path`, DuckDB en mémoire) plutôt que de mocker. Les fixtures ajoutées
ici doivent rester génériques ; les factories spécifiques à un module
vivent dans le `test_<module>.py` correspondant si elles ne sont utilisées
qu'une fois.
"""
