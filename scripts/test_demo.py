#!/usr/bin/env python3
"""Test GliceMia without Telegram — verify all components work.

Usage: python scripts/test_demo.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import init_db, get_session
from app.config import settings


def test_database():
    """Test DB and data availability."""
    from app.models import GlucoseReading, BolusEvent, PatientProfile
    s = get_session()
    glucose = s.query(GlucoseReading).count()
    bolus = s.query(BolusEvent).count()
    profile = s.query(PatientProfile).first()
    s.close()

    assert glucose > 0, "No glucose readings — run seed_demo.py first"
    assert profile is not None, "No patient profile — run seed_demo.py first"
    print(f"  DB: {glucose} readings, {bolus} boluses, profile={profile.name}")
    return True


def test_metrics():
    """Test metrics computation."""
    from datetime import datetime, timedelta
    from app.analytics.metrics import compute_metrics, time_slot_analysis

    s = get_session()
    # Use March 2026 range (known data)
    start = datetime(2026, 3, 1)
    end = datetime(2026, 3, 19)
    m = compute_metrics(s, start, end)
    assert m is not None, "Metrics returned None"
    assert 0 <= m["tir"] <= 100, f"TIR out of range: {m['tir']}"

    slots = time_slot_analysis(s, start, end)
    s.close()

    print(f"  Metrics: TIR={m['tir']}%, GMI={m['gmi']}%, CV={m['cv']}%, mean={m['mean_sg']}")
    print(f"  Slots: {len(slots)} time periods analyzed")
    return True


def test_patterns():
    """Test pattern data."""
    from app.models import GlucosePattern
    s = get_session()
    count = s.query(GlucosePattern).count()
    hourly = s.query(GlucosePattern).filter_by(period_type="hourly").count()
    s.close()
    assert count > 0, "No patterns — run seed_demo.py first"
    print(f"  Patterns: {count} total ({hourly} hourly)")
    return True


def test_context():
    """Test AI context builder."""
    from app.ai.context import build_context
    s = get_session()
    ctx = build_context(s)
    s.close()
    assert len(ctx) > 50, "Context too short"
    print(f"  Context: {len(ctx)} chars")
    # Show snippet
    for line in ctx.split("\n")[:3]:
        if line.strip():
            print(f"    {line[:80]}")
    return True


def test_system_prompt():
    """Test system prompt generation."""
    from app.ai.system_prompt import build_system_prompt
    prompt = build_system_prompt("TestUser", "it", "CURRENT STATUS: 135 mg/dL FLAT")
    assert "TestUser" in prompt
    assert "GliceMia" in prompt
    print(f"  System prompt: {len(prompt)} chars")
    return True


def test_report():
    """Test report generation."""
    from app.reports.generator import generate_report
    s = get_session()
    text, chart = generate_report(s, period="week", patient_name="TestUser", lang="it")
    s.close()
    assert text and len(text) > 50
    print(f"  Report: {len(text)} chars text")
    if chart:
        print(f"  Chart: {len(chart)} bytes PNG")
        with open("/tmp/glicemia_test_chart.png", "wb") as f:
            f.write(chart)
        print(f"  Saved: /tmp/glicemia_test_chart.png")
    return True


def test_estimator():
    """Test bolus estimation."""
    from app.analytics.estimator import estimate_bolus, predict_glucose
    s = get_session()
    bolus = estimate_bolus(s, carbs_g=50)
    pred = predict_glucose(s, minutes_ahead=60)
    s.close()
    print(f"  Bolus estimate for 50g carbs: {bolus}")
    print(f"  Glucose prediction 60min: {pred}")
    return True


def test_alerts():
    """Test alert engine."""
    from app.alerts.engine import check_alerts
    s = get_session()
    alerts = check_alerts(s)
    s.close()
    print(f"  Alerts: {len(alerts)} active")
    for a in alerts[:3]:
        print(f"    [{a.severity}] {a.alert_type}: sg={a.sg}, predicted={a.predicted_sg}")
    return True


async def test_ai_call():
    """Test LiteLLM call (requires API key)."""
    from app.ai.llm import chat as ai_chat

    if not (os.getenv("GEMINI_API_KEY") or os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY")):
        print("  AI: SKIPPED (no API key set)")
        return True

    response = await ai_chat([
        {"role": "system", "content": "You are a helpful assistant. Reply in one sentence."},
        {"role": "user", "content": "What is Type 1 Diabetes?"},
    ], max_tokens=100)
    print(f"  AI response: {response[:100]}")
    return True


def test_i18n():
    """Test multilingual messages."""
    from app.i18n.messages import msg
    for lang in ["it", "en", "es", "fr"]:
        welcome = msg("welcome", lang, name="TestUser")
        assert "TestUser" in welcome, f"Missing name in {lang} welcome"
    print("  i18n: IT/EN/ES/FR all OK")
    return True


def main():
    print("=== GliceMia — Component Tests ===\n")
    init_db()

    tests = [
        ("Database", test_database),
        ("Metrics", test_metrics),
        ("Patterns", test_patterns),
        ("Context", test_context),
        ("System Prompt", test_system_prompt),
        ("Report", test_report),
        ("Estimator", test_estimator),
        ("Alerts", test_alerts),
        ("i18n", test_i18n),
    ]

    passed = 0
    failed = 0
    for name, fn in tests:
        try:
            print(f"\n[{name}]")
            fn()
            passed += 1
        except Exception as e:
            print(f"  FAILED: {e}")
            failed += 1

    # Async test
    print(f"\n[AI Call]")
    try:
        asyncio.run(test_ai_call())
        passed += 1
    except Exception as e:
        print(f"  FAILED: {e}")
        failed += 1

    print(f"\n=== Results: {passed} passed, {failed} failed ===")
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
