from datetime import datetime
from zoneinfo import ZoneInfo

from src.strategy.late_peak_risk import compute_late_peak_risk
from src.weather.models import TemperatureSample


def test_late_peak_risk_increases_with_positive_trend():
    tz = ZoneInfo("Europe/Paris")
    now = datetime(2026, 3, 3, 18, 30, tzinfo=tz)
    samples = [
        TemperatureSample(timestamp=datetime(2026, 3, 3, 15, 0, tzinfo=tz), temperature_c=14.0),
        TemperatureSample(timestamp=datetime(2026, 3, 3, 18, 0, tzinfo=tz), temperature_c=16.0),
    ]
    score, reasons = compute_late_peak_risk(samples, samples[-1].timestamp, now)
    assert score > 0.5
    assert any("trend" in r for r in reasons)


def test_late_peak_risk_decays_late_evening_without_trend():
    tz = ZoneInfo("Europe/Paris")
    now = datetime(2026, 3, 3, 22, 0, tzinfo=tz)
    samples = [
        TemperatureSample(timestamp=datetime(2026, 3, 3, 20, 0, tzinfo=tz), temperature_c=14.0),
        TemperatureSample(timestamp=datetime(2026, 3, 3, 22, 0, tzinfo=tz), temperature_c=13.8),
    ]
    score, _ = compute_late_peak_risk(samples, samples[0].timestamp, now)
    assert score < 0.5
