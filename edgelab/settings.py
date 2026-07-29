"""Stockage local des clés API (London Strategic Edge et suivantes).

Trois décisions de design, dans l'ordre d'importance.

**Une clé n'est jamais relue par une API publique.** `describe()` renvoie
l'existence d'une clé, sa provenance et ses quatre derniers caractères — jamais
sa valeur. `resolve()` renvoie la valeur et n'est appelée que par le code qui
construit un client vers le fournisseur. Aucune route HTTP ne renvoie de secret,
même en lecture authentifiée : le seul moyen de récupérer une clé posée ici est
de lire le fichier sur disque, ce qui suppose déjà un accès à la machine.

**La variable d'environnement gagne sur le fichier.** Si `LSE_API_KEY` est
exportée, elle est utilisée même si le fichier contient autre chose. L'inverse
rendrait un déploiement imprévisible : on croit configurer par l'environnement
et un fichier oublié décide à sa place. `describe()` expose la provenance
effective pour que ce ne soit jamais une surprise.

**Le fichier est en 0600, dans l'état local, hors du dépôt.** Même répertoire
que le registre et le lockbox, déjà ignoré par git. Le format est celui d'un
`.env` (`CLE=valeur`, une par ligne) pour rester lisible et éditable à la main,
et sourçable dans un shell sans outil supplémentaire.
"""

from __future__ import annotations

import logging
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from edgelab.config import DEFAULT_CREDENTIALS_FILE

logger = logging.getLogger(__name__)

_ENV_VAR_PATTERN: Final = re.compile(r"^[A-Z][A-Z0-9_]*$")
_MASK_VISIBLE_CHARS: Final = 4
"""Caractères de fin laissés visibles : assez pour reconnaître une clé, pas pour l'utiliser."""

_SHORT_SECRET_LENGTH: Final = 8
"""En dessous, même les quatre derniers caractères en révèlent trop : on ne montre rien."""


class CredentialError(ValueError):
    """Levée quand un nom de clé ou une valeur est invalide."""


@dataclass(frozen=True)
class CredentialSpec:
    """Un emplacement de clé connu d'EdgeLab.

    `wired` distingue une clé réellement lue par un module de la plateforme
    d'une clé simplement rangée ici en attendant d'être utilisée. La distinction
    est affichée dans l'UI : un emplacement rempli mais non branché ne fait rien,
    et laisser croire le contraire serait un mensonge de plus dans un outil dont
    le but est de ne pas s'en raconter.
    """

    env_var: str
    label: str
    description: str
    docs_url: str
    wired: bool


KNOWN_CREDENTIALS: Final[tuple[CredentialSpec, ...]] = (
    CredentialSpec(
        env_var="LSE_API_KEY",
        label="London Strategic Edge",
        description=(
            "Catalogue, barres historiques et exports Parquet du vault. "
            "Lue par edgelab.data.lse à chaque appel au fournisseur."
        ),
        docs_url="https://londonstrategicedge.com/data",
        wired=True,
    ),
)

_KNOWN_BY_ENV_VAR: Final = {spec.env_var: spec for spec in KNOWN_CREDENTIALS}


@dataclass(frozen=True)
class CredentialStatus:
    """L'état d'un emplacement de clé, sans jamais porter la valeur elle-même."""

    env_var: str
    label: str
    description: str
    docs_url: str
    wired: bool
    configured: bool
    source: str
    """`environment`, `file` ou `absent` — la provenance effective, précédence appliquée."""
    hint: str
    """Les derniers caractères de la clé, ou une chaîne vide. Jamais la clé entière."""


def mask(secret: str) -> str:
    """Représentation affichable d'un secret : les quatre derniers caractères au plus.

    Une clé courte ne montre rien du tout — sur huit caractères, en révéler
    quatre coupe l'espace de recherche de moitié, ce qui n'est plus un indice
    mais une fuite.
    """
    if len(secret) < _SHORT_SECRET_LENGTH:
        return "•" * len(secret)
    return "•" * (len(secret) - _MASK_VISIBLE_CHARS) + secret[-_MASK_VISIBLE_CHARS:]


def validate_env_var(env_var: str) -> str:
    """Vérifie qu'un nom d'emplacement est un nom de variable d'environnement valide.

    Raises:
        CredentialError: si le nom n'est pas en majuscules ASCII, chiffres et
            tirets bas, commençant par une lettre.
    """
    candidate = env_var.strip()
    if not _ENV_VAR_PATTERN.match(candidate):
        raise CredentialError(
            f"nom de clé invalide : {env_var!r} — attendu MAJUSCULES_AVEC_TIRETS_BAS "
            "(ex. LSE_API_KEY)"
        )
    return candidate


class CredentialStore:
    """Lecture et écriture du fichier de clés local, en 0600."""

    def __init__(self, path: Path | str | None = None) -> None:
        """`path` omis, le défaut est lu à l'appel et non figé à l'import.

        La différence compte : un défaut évalué à la définition rend le chemin
        impossible à rediriger (tests, environnements multiples) une fois le
        module chargé.
        """
        self._path = Path(path) if path is not None else DEFAULT_CREDENTIALS_FILE

    @property
    def path(self) -> Path:
        """Le fichier où les clés sont écrites — à afficher, jamais son contenu."""
        return self._path

    def read_all(self) -> dict[str, str]:
        """Toutes les clés du fichier. Une ligne malformée est ignorée, pas fatale.

        Ignorer plutôt que lever : ce fichier est éditable à la main, et rendre
        toute la plateforme inutilisable à cause d'une ligne collée de travers
        serait un mauvais échange.
        """
        if not self._path.is_file():
            return {}
        entries: dict[str, str] = {}
        for raw in self._path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, _, value = line.partition("=")
            name = name.strip()
            if _ENV_VAR_PATTERN.match(name):
                entries[name] = value.strip().strip('"').strip("'")
        return entries

    def set(self, env_var: str, value: str) -> None:
        """Écrit ou remplace une clé, puis restreint le fichier à son propriétaire.

        Raises:
            CredentialError: si le nom est invalide ou la valeur vide.
        """
        name = validate_env_var(env_var)
        secret = value.strip()
        if not secret:
            raise CredentialError(f"valeur vide pour {name} — utiliser `unset` pour supprimer")
        entries = self.read_all()
        entries[name] = secret
        self._write(entries)
        logger.info("credential stored env_var=%s file=%s", name, self._path)

    def unset(self, env_var: str) -> bool:
        """Supprime une clé du fichier. Renvoie `False` si elle n'y était pas."""
        name = validate_env_var(env_var)
        entries = self.read_all()
        if name not in entries:
            return False
        del entries[name]
        self._write(entries)
        logger.info("credential removed env_var=%s file=%s", name, self._path)
        return True

    def _write(self, entries: dict[str, str]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.parent.chmod(stat.S_IRWXU)
        body = "".join(f"{name}={value}\n" for name, value in sorted(entries.items()))
        # Créer le fichier déjà restreint plutôt que l'ouvrir puis le durcir :
        # sinon il existe une fenêtre, si courte soit-elle, où la clé est
        # lisible par tout le monde sur la machine.
        descriptor = os.open(
            self._path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, stat.S_IRUSR | stat.S_IWUSR
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(
                "# EdgeLab — clés API locales. Ne jamais committer ce fichier.\n"
                "# Une variable d'environnement du même nom a la priorité sur ce fichier.\n"
            )
            handle.write(body)
        self._path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def resolve(env_var: str, *, store: CredentialStore | None = None) -> str | None:
    """La valeur effective d'une clé : environnement d'abord, fichier ensuite.

    Seule fonction du module qui renvoie un secret en clair. Tout le reste
    (CLI, API, UI) passe par `describe`, qui n'en renvoie jamais.
    """
    from_env = os.environ.get(env_var, "").strip()
    if from_env:
        return from_env
    entries = (store or CredentialStore()).read_all()
    value = entries.get(env_var, "").strip()
    return value or None


def describe(store: CredentialStore | None = None) -> list[CredentialStatus]:
    """L'état de chaque emplacement de clé, masqué — jamais la valeur.

    Les emplacements connus d'EdgeLab viennent en premier, puis les clés
    supplémentaires trouvées dans le fichier, marquées `wired=False` : rangées
    ici mais lues par rien.
    """
    entries = (store or CredentialStore()).read_all()
    extra = sorted(set(entries) - set(_KNOWN_BY_ENV_VAR))
    specs = [
        *KNOWN_CREDENTIALS,
        *(
            CredentialSpec(
                env_var=name,
                label=name,
                description="Clé enregistrée par l'utilisateur. Aucun module d'EdgeLab ne la lit.",
                docs_url="",
                wired=False,
            )
            for name in extra
        ),
    ]
    statuses = []
    for spec in specs:
        from_env = os.environ.get(spec.env_var, "").strip()
        from_file = entries.get(spec.env_var, "").strip()
        value = from_env or from_file
        source = "environment" if from_env else ("file" if from_file else "absent")
        statuses.append(
            CredentialStatus(
                env_var=spec.env_var,
                label=spec.label,
                description=spec.description,
                docs_url=spec.docs_url,
                wired=spec.wired,
                configured=bool(value),
                source=source,
                hint=mask(value) if value else "",
            )
        )
    return statuses
