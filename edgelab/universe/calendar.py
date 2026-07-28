"""Calendrier de session d'un instrument : quand des barres sont attendues.

Les horaires de session sont définis en heure locale de la place de cotation
plutôt qu'en UTC : c'est ce qui permet au calendrier de suivre correctement
les changements d'heure (DST) sans callback spécial — `zoneinfo` convertit
chaque jour de calendrier local en bornes UTC, et ces bornes glissent
automatiquement de +/-1h aux dates de bascule DST.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

_MAX_WEEKDAY = 6  # datetime.weekday(): lundi=0 .. dimanche=6


@dataclass(frozen=True)
class SessionWindow:
    """Une fenêtre de trading hebdomadaire, en heure locale de la place.

    `weekday` suit la convention `datetime.weekday()` (lundi=0 .. dimanche=6)
    et désigne le jour local d'*ouverture* de la fenêtre. Si `close` <=
    `open`, la fenêtre s'étend au-delà de minuit local et se termine le jour
    suivant (ex. session FX dimanche 22:00 -> lundi 22:00 n'existe pas telle
    quelle : on modélise plutôt une fenêtre par jour ouvré qui se termine le
    lendemain).
    """

    weekday: int
    open: time
    close: time

    def __post_init__(self) -> None:
        if not 0 <= self.weekday <= _MAX_WEEKDAY:
            raise ValueError(f"weekday must be in [0, 6], got {self.weekday}")

    @property
    def spans_midnight(self) -> bool:
        """Vrai si la fenêtre se termine le jour local suivant."""
        return self.close <= self.open


@dataclass(frozen=True)
class SessionCalendar:
    """Calendrier de session d'un instrument.

    `timezone` est le fuseau *local* de la place de cotation (ex.
    `"America/Chicago"` pour le CME, `"UTC"` pour un FX 24/5 simplifié).
    `holidays` liste des dates locales sans trading — un jour absent de
    `holidays` mais sans barre reste une anomalie (`session_gaps`), un jour
    présent dans `holidays` avec des barres devient l'anomalie inverse
    (`holiday_anomalies`), toutes deux détectées par `data.integrity`.
    """

    timezone: str
    windows: tuple[SessionWindow, ...]
    holidays: frozenset[date] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        # Valide le fuseau immédiatement plutôt qu'à la première utilisation.
        ZoneInfo(self.timezone)

    def is_holiday(self, local_date: date) -> bool:
        """Vrai si `local_date` est déclaré férié pour cet instrument."""
        return local_date in self.holidays

    def session_bounds_utc(self, local_date: date) -> tuple[datetime, datetime] | None:
        """Bornes UTC (début inclus, fin exclue) de la session qui s'ouvre `local_date`.

        Renvoie `None` si aucune fenêtre ne s'ouvre ce jour-là ou si le jour
        est férié.
        """
        if self.is_holiday(local_date):
            return None
        window = next((w for w in self.windows if w.weekday == local_date.weekday()), None)
        if window is None:
            return None
        tz = ZoneInfo(self.timezone)
        start_local = datetime.combine(local_date, window.open, tzinfo=tz)
        close_date = local_date + timedelta(days=1) if window.spans_midnight else local_date
        end_local = datetime.combine(close_date, window.close, tzinfo=tz)
        return start_local.astimezone(UTC), end_local.astimezone(UTC)

    def expected_bar_starts(
        self, start: datetime, end: datetime, frequency: timedelta
    ) -> list[datetime]:
        """Horodatages UTC des débuts de barre attendus dans `[start, end)`.

        Itère les jours de calendrier locaux couvrant `[start, end)`, résout
        les bornes de session de chacun, puis découpe chaque session en pas
        de `frequency`.
        """
        if frequency <= timedelta(0):
            raise ValueError("frequency must be positive")
        tz = ZoneInfo(self.timezone)
        expected: list[datetime] = []
        for local_day in _iter_local_dates(start, end, tz):
            bounds = self.session_bounds_utc(local_day)
            if bounds is None:
                continue
            session_start, session_end = bounds
            cursor = max(session_start, start)
            session_end = min(session_end, end)
            while cursor < session_end:
                expected.append(cursor)
                cursor += frequency
        return expected


def _iter_local_dates(start: datetime, end: datetime, tz: ZoneInfo) -> Iterator[date]:
    """Dates locales (dans `tz`) couvrant `[start, end)`, une par jour civil."""
    current = start.astimezone(tz).date() - timedelta(days=1)
    last = end.astimezone(tz).date() + timedelta(days=1)
    while current <= last:
        yield current
        current += timedelta(days=1)
