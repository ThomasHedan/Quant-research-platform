"""Tests de edgelab.data.integrity (contrôle d'intégrité obligatoire, Phase 1)."""

from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta

import polars as pl
import pytest
from edgelab.data.integrity import (
    IntegrityIssue,
    IntegrityReport,
    IntegritySeverity,
    run_integrity_checks,
)
from edgelab.universe.calendar import SessionCalendar, SessionWindow
from edgelab.universe.instrument import Instrument

FREQUENCY = timedelta(minutes=1)
START = datetime(2024, 1, 8, 0, 0, tzinfo=UTC)  # lundi
END = datetime(2024, 1, 9, 0, 0, tzinfo=UTC)  # mardi


def test_clean_dataset_has_no_critical_issues(
    eurusd: Instrument, make_clean_bars: Callable[..., pl.DataFrame]
) -> None:
    """Un dataset construit sur les horodatages attendus ne déclenche aucune anomalie critique."""
    bars = make_clean_bars(eurusd, start=START, end=END, frequency=FREQUENCY)

    report = run_integrity_checks(bars, eurusd.session_calendar, frequency=FREQUENCY)

    assert report.is_clean


def test_artificial_session_gap_is_detected_and_critical(
    eurusd: Instrument, make_clean_bars: Callable[..., pl.DataFrame]
) -> None:
    """Critère d'acceptation Phase 1 : un trou de session artificiel est détecté."""
    bars = make_clean_bars(eurusd, start=START, end=END, frequency=FREQUENCY)
    gapped = bars.filter(
        ~pl.col("timestamp").is_between(
            datetime(2024, 1, 8, 10, 0, tzinfo=UTC),
            datetime(2024, 1, 8, 10, 30, tzinfo=UTC),
            closed="left",
        )
    )

    report = run_integrity_checks(gapped, eurusd.session_calendar, frequency=FREQUENCY)

    gaps = [i for i in report.issues if i.kind == "session_gaps"]
    assert len(gaps) == 1
    assert gaps[0].severity is IntegritySeverity.CRITICAL
    assert gaps[0].count == 30
    assert not report.is_clean


def test_duplicate_bars_are_detected_and_critical(
    eurusd: Instrument, make_clean_bars: Callable[..., pl.DataFrame]
) -> None:
    """Des barres dupliquées sont détectées comme critiques."""
    bars = make_clean_bars(eurusd, start=START, end=END, frequency=FREQUENCY)
    duplicated = pl.concat([bars, bars[0:3]])

    report = run_integrity_checks(duplicated, eurusd.session_calendar, frequency=FREQUENCY)

    dups = [i for i in report.issues if i.kind == "duplicate_bars"]
    assert len(dups) == 1
    assert dups[0].severity is IntegritySeverity.CRITICAL
    assert dups[0].count == 3
    assert not report.is_clean


def test_aberrant_tick_is_flagged_as_warning_not_critical(
    eurusd: Instrument, make_clean_bars: Callable[..., pl.DataFrame]
) -> None:
    """Un mouvement de prix extrême est signalé en avertissement, sans mettre en quarantaine."""
    bars = make_clean_bars(eurusd, start=START, end=END, frequency=FREQUENCY)
    spiked = bars.with_columns(
        pl.when(pl.int_range(pl.len()) == 500)
        .then(pl.col("close") * 10)
        .otherwise(pl.col("close"))
        .alias("close")
    )

    report = run_integrity_checks(spiked, eurusd.session_calendar, frequency=FREQUENCY)

    aberrant = [i for i in report.issues if i.kind == "aberrant_ticks"]
    assert len(aberrant) == 1
    assert aberrant[0].severity is IntegritySeverity.WARNING
    assert report.is_clean  # un warning seul ne déclenche pas la quarantaine


def test_zero_volume_bars_are_flagged_as_warning(
    eurusd: Instrument, make_clean_bars: Callable[..., pl.DataFrame]
) -> None:
    """Des barres à volume nul sont signalées sans déclencher la quarantaine."""
    bars = make_clean_bars(eurusd, start=START, end=END, frequency=FREQUENCY)
    zeroed = bars.with_columns(
        pl.when(pl.int_range(pl.len()) < 5).then(0.0).otherwise(pl.col("volume")).alias("volume")
    )

    report = run_integrity_checks(zeroed, eurusd.session_calendar, frequency=FREQUENCY)

    zero_volume = [i for i in report.issues if i.kind == "zero_volume"]
    assert len(zero_volume) == 1
    assert zero_volume[0].count == 5
    assert zero_volume[0].severity is IntegritySeverity.WARNING
    assert report.is_clean


def test_zero_volume_check_is_skipped_when_check_volume_is_false(
    eurusd: Instrument, make_clean_bars: Callable[..., pl.DataFrame]
) -> None:
    """`check_volume=False` désactive explicitement le contrôle de volume nul."""
    bars = make_clean_bars(eurusd, start=START, end=END, frequency=FREQUENCY)
    zeroed = bars.with_columns(pl.lit(0.0).alias("volume"))

    report = run_integrity_checks(
        zeroed, eurusd.session_calendar, frequency=FREQUENCY, check_volume=False
    )

    assert not any(i.kind == "zero_volume" for i in report.issues)


def test_holiday_with_bars_present_is_flagged_as_anomaly(eurusd: Instrument) -> None:
    """Des barres présentes sur un jour férié déclaré sont une anomalie signalée."""
    holiday = datetime(2024, 1, 8, tzinfo=UTC).date()
    calendar_with_holiday = SessionCalendar(
        timezone=eurusd.session_calendar.timezone,
        windows=eurusd.session_calendar.windows,
        holidays=frozenset({holiday}),
    )
    timestamps = eurusd.session_calendar.expected_bar_starts(START, END, FREQUENCY)
    bars = pl.DataFrame(
        [(ts, 1.1, 1.1001, 1.0999, 1.1, 100.0) for ts in timestamps[:5]],
        schema=["timestamp", "open", "high", "low", "close", "volume"],
        orient="row",
    )

    report = run_integrity_checks(bars, calendar_with_holiday, frequency=FREQUENCY)

    holiday_issues = [i for i in report.issues if i.kind == "holiday_anomalies"]
    assert len(holiday_issues) == 1
    assert holiday_issues[0].severity is IntegritySeverity.WARNING


def test_dst_transition_is_flagged_as_informational_warning() -> None:
    """Une bascule DST dans la période est signalée à titre informatif, sans quarantaine seule."""
    calendar = SessionCalendar(
        timezone="Europe/Paris",
        windows=tuple(
            SessionWindow(weekday=d, open=time(9, 0), close=time(17, 0)) for d in range(5)
        ),
    )
    before = calendar.session_bounds_utc(date(2024, 3, 29))  # vendredi, avant bascule (UTC+1)
    after = calendar.session_bounds_utc(date(2024, 4, 1))  # lundi, après bascule (UTC+2)
    assert before is not None
    assert after is not None
    bars = pl.DataFrame(
        [
            (before[0], 1.1, 1.1001, 1.0999, 1.1, 100.0),
            (after[0], 1.1, 1.1001, 1.0999, 1.1, 100.0),
        ],
        schema=["timestamp", "open", "high", "low", "close", "volume"],
        orient="row",
    )

    report = run_integrity_checks(bars, calendar, frequency=timedelta(hours=1), check_volume=False)

    dst_issues = [i for i in report.issues if i.kind == "dst_transitions"]
    assert len(dst_issues) == 1
    assert dst_issues[0].severity is IntegritySeverity.WARNING


def test_empty_dataset_produces_no_issues(eurusd: Instrument) -> None:
    """Un dataset vide ne fait planter aucun contrôle et ne signale rien."""
    empty = pl.DataFrame(
        schema={
            "timestamp": pl.Datetime("us", "UTC"),
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "volume": pl.Float64,
        }
    )

    report = run_integrity_checks(empty, eurusd.session_calendar, frequency=FREQUENCY)

    assert report.issues == ()
    assert report.is_clean


def test_report_summary_lists_every_issue() -> None:
    """`summary()` produit une ligne lisible par anomalie, ou un message neutre si aucune."""
    empty_report = IntegrityReport(issues=())
    assert "aucune anomalie" in empty_report.summary()

    report = IntegrityReport(
        issues=(
            IntegrityIssue(
                kind="session_gaps", severity=IntegritySeverity.CRITICAL, message="x", count=2
            ),
        )
    )
    assert "session_gaps" in report.summary()
    assert "critical" in report.summary()


def test_critical_issues_filters_out_warnings() -> None:
    """`critical_issues` ne renvoie que les anomalies bloquantes."""
    warning = IntegrityIssue(
        kind="zero_volume", severity=IntegritySeverity.WARNING, message="w", count=1
    )
    critical = IntegrityIssue(
        kind="duplicate_bars", severity=IntegritySeverity.CRITICAL, message="c", count=1
    )
    report = IntegrityReport(issues=(warning, critical))

    assert report.critical_issues() == (critical,)


@pytest.mark.parametrize("bad_frequency", [timedelta(0), timedelta(seconds=-1)])
def test_run_integrity_checks_propagates_calendar_frequency_validation(
    eurusd: Instrument, bad_frequency: timedelta
) -> None:
    """Une fréquence non positive est refusée par le calendrier sous-jacent."""
    bars = pl.DataFrame(
        [(START, 1.1, 1.1, 1.1, 1.1, 1.0)],
        schema=["timestamp", "open", "high", "low", "close", "volume"],
        orient="row",
    )

    with pytest.raises(ValueError, match="frequency"):
        run_integrity_checks(bars, eurusd.session_calendar, frequency=bad_frequency)
