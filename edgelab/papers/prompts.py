"""Prompts copiables pour l'extraction de papier et le brouillon d'hypothèse (Phase 7).

Ce premier jet ne construit pas d'extraction PDF ni de traduction en
interne : ce travail est délégué à une IA généraliste, via ces deux prompts
que l'utilisateur copie, exécute ailleurs, puis colle la réponse JSON dans
l'UI. Les prompts vivent ici — pas seulement dans le frontend — pour que
leur schéma JSON soit un seul contrat, partagé avec `PaperAnalysisRequest`
et `HypothesisDraftRequest` (`edgelab.papers.models`) : un changement de
champ se fait à un seul endroit.

Le second prompt s'arrête délibérément à un brouillon d'hypothèse et un
squelette de code non exécuté — jamais à un backtest. Faire tourner ce
squelette est une action CLI distincte, volontaire, qui reste à construire
(voir `edgelab/strategies/README.md`) ; ce module ne l'implémente pas.
"""

from __future__ import annotations

from edgelab.papers.models import PaperSheet

# Prompt statique : l'utilisateur colle le texte du papier à la suite avant de l'envoyer.
PAPER_ANALYSIS_PROMPT = """\
Tu es un assistant de recherche quantitative. On te donne un papier de \
recherche académique ou un preprint (texte, lien ou PDF collé ci-dessous) \
portant sur une anomalie ou un effet potentiellement exploitable sur les \
marchés financiers.

Détecte la langue d'origine du papier. Quelle qu'elle soit, rédige TOUTES \
les valeurs textuelles de la fiche ci-dessous EN FRANÇAIS — seul le champ \
"language_source" porte le code de la langue d'origine (ISO 639-1, ex: \
"zh" pour le chinois, "ja" pour le japonais, "en" pour l'anglais). Ne \
rejette jamais un papier parce qu'il n'est pas en anglais.

Ne recopie jamais le texte intégral du papier : uniquement les champs de \
métadonnées demandés ci-dessous, résumés dans tes propres mots.

Réponds UNIQUEMENT avec un objet JSON valide, sans balise markdown et sans \
commentaire, correspondant exactement à ce schéma :

{
  "title": "titre du papier, en langue originale",
  "authors": ["Nom Auteur 1", "Nom Auteur 2"],
  "publication_year": 2019,
  "language_source": "code ISO 639-1 de la langue d'origine, ex: zh",
  "venue": "revue ou preprint, ex: SSRN, Journal of Finance",
  "anomaly_family": "famille d'anomalie, en français, ex: momentum, value, microstructure",
  "asset_class": "classe d'actifs étudiée, en français, ex: FX, futures matières premières",
  "frequency": "fréquence des données, ex: quotidien, intraday M15",
  "sample_period": "période d'échantillon, ex: 1990-2015",
  "claimed_sharpe_or_hit_rate": "chiffre(s) revendiqué(s) par le papier, en texte libre",
  "costs_considered": "oui | non | partiel",
  "economic_hypothesis": "l'hypothèse économique du papier en UNE phrase, en français",
  "data_needed": "données nécessaires pour répliquer, en français",
  "replication_difficulty": "faible | moyenne | elevee",
  "instrument_available_at_prop_firms": true | false,
  "data_accessible": true | false,
  "mechanizable_without_discretion": true | false,
  "personal_notes": "remarques éventuelles, en français, laisse vide si aucune",
  "source_url_or_doi": "URL ou DOI si connu, laisse vide sinon"
}

Pour "instrument_available_at_prop_firms", "data_accessible" et \
"mechanizable_without_discretion" : ce sont des estimations. Sois honnête \
si tu n'es pas sûr plutôt que de deviner de façon optimiste — l'utilisateur \
les vérifiera avant de s'y fier.

Voici le papier :

"""


def hypothesis_draft_prompt_for(sheet: PaperSheet) -> str:
    """Prompt personnalisé au papier `sheet`, sa fiche étant injectée comme contexte.

    Demande un brouillon d'hypothèse falsifiable + un squelette de code —
    jamais un backtest, jamais du code connecté aux données réelles
    d'EdgeLab (voir le docstring du module).
    """
    sheet_json = sheet.model_dump_json(indent=2)
    return f"""\
Tu es un assistant de recherche quantitative rigoureux. Ta tâche n'est PAS \
de convaincre que cette idée fonctionne — elle est de formuler une \
hypothèse strictement falsifiable et un squelette de stratégie testable, \
pour qu'un humain puisse ensuite essayer de la tuer avec un protocole de \
validation statistique.

Voici la fiche du papier source :

{sheet_json}

Réponds UNIQUEMENT avec un objet JSON valide, sans balise markdown et sans \
commentaire, correspondant exactement à ce schéma :

{{
  "economic_hypothesis": "hypothèse économique en UNE phrase, en français",
  "predicted_direction": "long | short | both",
  "predicted_amplitude_atr": 0.5,
  "predicted_hit_rate": 0.55,
  "predicted_horizon_bars": 20,
  "where_it_should_not_work": "OBLIGATOIRE, non vide : dans quelles conditions précises \
cet effet doit disparaître (régime, sous-échantillon, univers). Non falsifiable sinon, \
sera refusée.",
  "kill_criteria": [
    {{"name": "nom court", "metric": "métrique mesurée, ex: t_stat, p_value, dsr, pbo",
     "comparison": "less_than | greater_than", "threshold": 2.0}}
  ],
  "strategy_code_skeleton": "code Python en texte brut (échappé pour JSON) : signal \
d'entrée, condition de sortie. Squelette non connecté aux données EdgeLab, non exécuté \
automatiquement."
}}

"kill_criteria" doit contenir au moins un critère.

Ce JSON ne lance AUCUN backtest automatiquement : il crée un brouillon que \
l'utilisateur devra faire passer par le CLI EdgeLab pour le tester \
réellement, avec ses propres critères de mort pré-enregistrés (I2).
"""
