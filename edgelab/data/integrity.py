"""Contrôle d'intégrité obligatoire à l'ingestion.

Chaque vérification a une sévérité fixée à l'avance : `CRITICAL` déclenche la
quarantaine (`session_gaps`, `duplicate_bars` — des défauts qui peuvent
biaiser un backtest), `WARNING` figure dans le rapport sans bloquer
(`aberrant_ticks`, `zero_volume`, `dst_transitions`, `holiday_anomalies` —
des faits qui demandent un jugement humain, pas un seuil automatique). Ce
n'est pas ce que le texte de la spec énumère à plat, mais traiter chaque
transition DST semestrielle comme une quarantaine rendrait l'outil inutile
sur toute série de plus de six mois ; voir `edgelab/data/README.md`.
"""

from __future__ import annotations

import enum
from datetime import datetime, timedelta
from typing import cast
from zoneinfo import ZoneInfo

import polars as pl
from pydantic import BaseModel, ConfigDict

from edgelab.universe.calendar import SessionCalendar

DEFAULT_ABERRANT_STD_WINDOW = 20
DEFAULT_ABERRANT_STD_THRESHOLD = 8.0


class IntegritySeverity(enum.StrEnum):
    """Gravité d'une anomalie détectée par le contrôle d'intégrité."""

    WARNING = "warning"
    CRITICAL = "critical"


class IntegrityIssue(BaseModel):
    """Une catégorie d'anomalie détectée, avec son décompte."""

    model_config = ConfigDict(frozen=True)

    kind: str
    severity: IntegritySeverity
    message: str
    count: int


class IntegrityReport(BaseModel):
    """Rapport de contrôle d'intégrité d'un dataset."""

    model_config = ConfigDict(frozen=True)

    issues: tuple[IntegrityIssue, ...]

    @property
    def is_clean(self) -> bool:
        """Vrai si aucune anomalie `CRITICAL` n'a été détectée."""
        return not any(issue.severity is IntegritySeverity.CRITICAL for issue in self.issues)

    def critical_issues(self) -> tuple[IntegrityIssue, ...]:
        """Les anomalies `CRITICAL`, celles qui déclenchent la quarantaine."""
        return tuple(i for i in self.issues if i.severity is IntegritySeverity.CRITICAL)

    def summary(self) -> str:
        """Résumé humainement lisible, une ligne par anomalie détectée."""
        if not self.issues:
            return "aucune anomalie détectée"
        return "; ".join(f"{i.kind}[{i.severity.value}]={i.count}" for i in self.issues)


def run_integrity_checks(  # noqa: PLR0913 — chaque contrôle a son propre seuil paramétrable
    bars: pl.DataFrame,
    calendar: SessionCalendar,
    *,
    frequency: timedelta,
    check_volume: bool = True,
    aberrant_std_window: int = DEFAULT_ABERRANT_STD_WINDOW,
    aberrant_std_threshold: float = DEFAULT_ABERRANT_STD_THRESHOLD,
) -> IntegrityReport:
    """Exécute tous les contrôles d'intégrité sur des barres OHLCV.

    `bars` doit contenir au minimum les colonnes `timestamp` (UTC),
    `open`, `high`, `low`, `close`, et `volume` si `check_volume`.
    Les lignes doivent être triées par `timestamp` (non revérifié ici : la
    responsabilité revient à l'appelant, qui connaît sa source).
    """
    issues: list[IntegrityIssue] = [
        *_check_session_gaps(bars, calendar, frequency),
        *_check_duplicate_bars(bars),
        *_check_aberrant_ticks(bars, aberrant_std_window, aberrant_std_threshold),
        *_check_holiday_anomalies(bars, calendar),
    ]
    if check_volume:
        issues.extend(_check_zero_volume(bars))
    issues.extend(_check_dst_transitions(bars, calendar))
    return IntegrityReport(issues=tuple(issues))


def _check_session_gaps(
    bars: pl.DataFrame, calendar: SessionCalendar, frequency: timedelta
) -> list[IntegrityIssue]:
    if bars.is_empty():
        return []
    start = cast(datetime, bars["timestamp"].min())
    end = cast(datetime, bars["timestamp"].max()) + frequency
    expected = set(calendar.expected_bar_starts(start, end, frequency))
    actual = set(bars["timestamp"].to_list())
    missing = expected - actual
    if not missing:
        return []
    return [
        IntegrityIssue(
            kind="session_gaps",
            severity=IntegritySeverity.CRITICAL,
            message=(
                f"{len(missing)} barre(s) de session attendue(s) et absente(s) "
                f"(ex. {sorted(missing)[0]})"
            ),
            count=len(missing),
        )
    ]


def _check_duplicate_bars(bars: pl.DataFrame) -> list[IntegrityIssue]:
    if bars.is_empty():
        return []
    counts = bars.group_by("timestamp").len()
    duplicated = counts.filter(pl.col("len") > 1)
    if duplicated.is_empty():
        return []
    extra = int((duplicated["len"] - 1).sum())
    return [
        IntegrityIssue(
            kind="duplicate_bars",
            severity=IntegritySeverity.CRITICAL,
            message=f"{duplicated.height} horodatage(s) dupliqué(s) ({extra} barre(s) en trop)",
            count=extra,
        )
    ]


def _check_aberrant_ticks(
    bars: pl.DataFrame, window: int, threshold: float
) -> list[IntegrityIssue]:
    if bars.height <= window:
        return []
    log_returns = (bars["close"] / bars["close"].shift(1)).log()
    # L'écart-type de référence exclut le rendement testé (shift(1)) : sinon
    # un pic isolé gonfle son propre écart-type de comparaison et échappe à
    # la détection.
    rolling_std = log_returns.shift(1).rolling_std(window_size=window)
    flagged = log_returns.abs() > (rolling_std * threshold)
    count = int(flagged.fill_null(False).sum())
    if count == 0:
        return []
    return [
        IntegrityIssue(
            kind="aberrant_ticks",
            severity=IntegritySeverity.WARNING,
            message=(
                f"{count} barre(s) avec un rendement > {threshold}x l'écart-type glissant "
                f"({window} barres)"
            ),
            count=count,
        )
    ]


def _check_zero_volume(bars: pl.DataFrame) -> list[IntegrityIssue]:
    if "volume" not in bars.columns or bars.is_empty():
        return []
    count = int((bars["volume"] == 0).sum())
    if count == 0:
        return []
    return [
        IntegrityIssue(
            kind="zero_volume",
            severity=IntegritySeverity.WARNING,
            message=f"{count} barre(s) à volume nul",
            count=count,
        )
    ]


def _check_dst_transitions(bars: pl.DataFrame, calendar: SessionCalendar) -> list[IntegrityIssue]:
    if bars.is_empty():
        return []
    offsets = {ts.astimezone(_zoneinfo(calendar)).utcoffset() for ts in bars["timestamp"]}
    if len(offsets) <= 1:
        return []
    return [
        IntegrityIssue(
            kind="dst_transitions",
            severity=IntegritySeverity.WARNING,
            message=(
                f"{len(offsets)} décalage(s) UTC distinct(s) observé(s) dans la période "
                "(changements d'heure normaux, à titre informatif)"
            ),
            count=len(offsets) - 1,
        )
    ]


def _check_holiday_anomalies(bars: pl.DataFrame, calendar: SessionCalendar) -> list[IntegrityIssue]:
    if not calendar.holidays or bars.is_empty():
        return []
    tz = _zoneinfo(calendar)
    local_dates = {ts.astimezone(tz).date() for ts in bars["timestamp"]}
    anomalies = local_dates & calendar.holidays
    if not anomalies:
        return []
    return [
        IntegrityIssue(
            kind="holiday_anomalies",
            severity=IntegritySeverity.WARNING,
            message=f"barres présentes sur {len(anomalies)} jour(s) férié(s) déclaré(s)",
            count=len(anomalies),
        )
    ]


def _zoneinfo(calendar: SessionCalendar) -> ZoneInfo:
    return ZoneInfo(calendar.timezone)
