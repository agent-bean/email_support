"""Expiry-safe polling for the opt-in live Google verification harness."""

import asyncio
import importlib.util
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from email_support.integrations.google_workspace import TokenProbeOutcome

SCRIPT = Path(__file__).resolve().parents[3] / "scripts/live-google-smoke.py"
SPEC = importlib.util.spec_from_file_location("live_google_smoke", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("live Google smoke script could not be loaded")
LIVE_GOOGLE_SMOKE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = LIVE_GOOGLE_SMOKE
SPEC.loader.exec_module(LIVE_GOOGLE_SMOKE)


@pytest.mark.asyncio
async def test_expiry_cutoff_is_pending_without_a_provider_probe() -> None:
    now = datetime(2026, 10, 26, 12, tzinfo=UTC)
    calls = 0

    async def probe() -> TokenProbeOutcome:
        nonlocal calls
        calls += 1
        return TokenProbeOutcome.REJECTED

    result = await LIVE_GOOGLE_SMOKE.poll_for_remote_rejection(
        probe,
        expires_at=now + timedelta(seconds=30),
        now=lambda: now,
        monotonic=lambda: 0.0,
        sleep=asyncio.sleep,
    )

    assert result is False
    assert calls == 0


@pytest.mark.asyncio
async def test_rejection_after_expiry_cutoff_is_not_revocation_evidence() -> None:
    now = [datetime(2026, 10, 26, 12, tzinfo=UTC)]
    expires_at = now[0] + timedelta(seconds=240)
    calls = 0

    async def probe() -> TokenProbeOutcome:
        nonlocal calls
        calls += 1
        now[0] = expires_at - timedelta(seconds=30)
        return TokenProbeOutcome.REJECTED

    result = await LIVE_GOOGLE_SMOKE.poll_for_remote_rejection(
        probe,
        expires_at=expires_at,
        now=lambda: now[0],
        monotonic=lambda: 0.0,
        sleep=asyncio.sleep,
    )

    assert result is False
    assert calls == 1


@pytest.mark.asyncio
async def test_accepted_token_is_polled_until_rejection_before_expiry_cutoff() -> None:
    now = datetime(2026, 10, 26, 12, tzinfo=UTC)
    monotonic = [0.0]
    calls = 0

    async def probe() -> TokenProbeOutcome:
        nonlocal calls
        calls += 1
        return TokenProbeOutcome.REJECTED if calls == 2 else TokenProbeOutcome.ACCEPTED

    async def advance(seconds: float) -> None:
        monotonic[0] += seconds

    result = await LIVE_GOOGLE_SMOKE.poll_for_remote_rejection(
        probe,
        expires_at=now + timedelta(seconds=240),
        now=lambda: now,
        monotonic=lambda: monotonic[0],
        sleep=advance,
    )

    assert result is True
    assert calls == 2


@pytest.mark.asyncio
async def test_probe_is_cancelled_at_the_observation_deadline() -> None:
    cancelled = False

    async def probe() -> TokenProbeOutcome:
        nonlocal cancelled
        try:
            await asyncio.sleep(1)
        except asyncio.CancelledError:
            cancelled = True
            raise
        return TokenProbeOutcome.ACCEPTED

    result = await LIVE_GOOGLE_SMOKE.poll_for_remote_rejection(
        probe,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        timeout_seconds=0.01,
        interval_seconds=0.01,
    )

    assert result is False
    assert cancelled is True
