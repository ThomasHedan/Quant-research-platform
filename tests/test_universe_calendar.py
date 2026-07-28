"""Tests de edgelab.universe.calendar."""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfoNotFoundError

import pytest
from edgelab.universe.calendar import SessionCalendar, SessionWindow


def test_session_window_rejects_invalid_weekday() -> None:
    """Un `weekday` hors [0, 6] est invalide."""
    with pytest.raises(ValueError, match="weekday"):
        SessionWindow(weekday=7, open=time(0, 0), close=time(0, 0))


def test_session_window_spans_midnight_when_close_before_open() -> None:
    """Une fenêtre close <= open s'étend au-delà de minuit local."""
    window = SessionWindow(weekday=6, open=time(22, 0), close=time(0, 0))

    assert window.spans_midnight is True


def test_session_window_does_not_span_midnight_for_a_same_day_window() -> None:
    """Une fenêtre close > open reste dans le même jour local."""
    window = SessionWindow(weekday=0, open=time(0, 0), close=time(22, 0))

    assert window.spans_midnight is False


def test_calendar_rejects_unknown_timezone() -> None:
    """Un fuseau invalide lève dès la construction, pas au premier usage."""
    with pytest.raises(ZoneInfoNotFoundError):
        SessionCalendar(timezone="Not/A_Zone", windows=())


def test_session_bounds_utc_none_on_a_day_with_no_window() -> None:
    """Un jour sans fenêtre définie (ex. samedi FX) n'a pas de session."""
    calendar = SessionCalendar(
        timezone="UTC", windows=(SessionWindow(weekday=0, open=time(0, 0), close=time(22, 0)),)
    )

    assert calendar.session_bounds_utc(date(2024, 1, 6)) is None  # samedi


def test_session_bounds_utc_none_on_a_holiday() -> None:
    """Un jour férié déclaré n'a pas de session, même s'il a une fenêtre."""
    holiday = date(2024, 1, 1)
    calendar = SessionCalendar(
        timezone="UTC",
        windows=(SessionWindow(weekday=0, open=time(0, 0), close=time(22, 0)),),
        holidays=frozenset({holiday}),
    )

    assert calendar.session_bounds_utc(holiday) is None


def test_session_bounds_utc_spans_into_next_day() -> None:
    """Une fenêtre qui traverse minuit local se termine le lendemain."""
    calendar = SessionCalendar(
        timezone="UTC", windows=(SessionWindow(weekday=6, open=time(22, 0), close=time(0, 0)),)
    )

    bounds = calendar.session_bounds_utc(date(2024, 1, 7))  # dimanche

    assert bounds is not None
    start, end = bounds
    assert start == datetime(2024, 1, 7, 22, 0, tzinfo=UTC)
    assert end == datetime(2024, 1, 8, 0, 0, tzinfo=UTC)


def test_session_bounds_utc_shifts_across_dst_transition() -> None:
    """Une session en heure locale glisse d'une heure UTC au changement DST.

    L'Europe passe à l'heure d'été le dernier dimanche de mars : une session
    "09:00-17:00 Europe/Paris" doit donc apparaître décalée d'une heure en
    UTC avant et après cette date, sans configuration DST explicite.
    """
    calendar = SessionCalendar(
        timezone="Europe/Paris",
        windows=tuple(
            SessionWindow(weekday=d, open=time(9, 0), close=time(17, 0)) for d in range(5)
        ),
    )

    before_dst = calendar.session_bounds_utc(date(2024, 3, 29))  # vendredi, avant bascule
    after_dst = calendar.session_bounds_utc(date(2024, 4, 1))  # lundi, après bascule

    assert before_dst is not None
    assert after_dst is not None
    assert before_dst[0].hour == 8  # UTC+1 (CET)
    assert after_dst[0].hour == 7  # UTC+2 (CEST)


def test_expected_bar_starts_steps_by_frequency_within_session() -> None:
    """Les horodatages attendus sont espacés exactement de `frequency`."""
    calendar = SessionCalendar(
        timezone="UTC", windows=(SessionWindow(weekday=0, open=time(0, 0), close=time(1, 0)),)
    )

    starts = calendar.expected_bar_starts(
        datetime(2024, 1, 1, tzinfo=UTC),
        datetime(2024, 1, 2, tzinfo=UTC),
        timedelta(minutes=15),
    )

    assert starts == [
        datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
        datetime(2024, 1, 1, 0, 15, tzinfo=UTC),
        datetime(2024, 1, 1, 0, 30, tzinfo=UTC),
        datetime(2024, 1, 1, 0, 45, tzinfo=UTC),
    ]


def test_expected_bar_starts_skips_days_without_a_session() -> None:
    """Aucun horodatage n'est produit pour un jour sans fenêtre ni férié."""
    calendar = SessionCalendar(
        timezone="UTC", windows=(SessionWindow(weekday=0, open=time(0, 0), close=time(1, 0)),)
    )

    starts = calendar.expected_bar_starts(
        datetime(2024, 1, 2, tzinfo=UTC),  # mardi : pas de fenêtre définie
        datetime(2024, 1, 3, tzinfo=UTC),
        timedelta(minutes=15),
    )

    assert starts == []


def test_expected_bar_starts_rejects_non_positive_frequency() -> None:
    """Une fréquence nulle ou négative n'a pas de sens et lève."""
    calendar = SessionCalendar(timezone="UTC", windows=())

    with pytest.raises(ValueError, match="frequency"):
        calendar.expected_bar_starts(
            datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 1, 2, tzinfo=UTC), timedelta(0)
        )
