from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from typing import Any

import pytest

from app.integrations.foundry_provider import FoundryProviderError
from app.services.goals_localization import semantic_qa_service
from app.services.goals_localization.semantic_qa_service import (
    FoundryRateGate,
    SemanticQAService,
)


class FakeProvider:
    def __init__(self, failures: int = 0, error: str = "Foundry HTTP 429: busy") -> None:
        self.failures = failures
        self.error = error
        self.calls = 0
        self.lock = threading.Lock()

    def _chat_json(self, *, system: str, user: str) -> dict[str, Any]:
        with self.lock:
            self.calls += 1
            if self.failures > 0:
                self.failures -= 1
                raise FoundryProviderError(self.error)
        return {
            "json": {
                "goal": {"text": "nieuw doel", "changed": True, "reason": "wrong target"},
                "description": {"text": "beschrijving", "changed": False, "reason": ""},
                "kra": {"text": "kra", "changed": False, "reason": ""},
            },
            "usage": SimpleNamespace(input_tokens=100, output_tokens=40),
        }


def _revise(service: SemanticQAService) -> Any:
    return service.revise_record(
        target_language="nl",
        source_goal="Grow revenue 10%",
        source_description="Increase ARR",
        source_kra="Revenue KRA",
        translated_goal="oud doel",
        translated_description="beschrijving",
        translated_kra="kra",
        preserve_terms=["KRA"],
    )


def test_gate_allows_requests_under_the_minute_limit() -> None:
    gate = FoundryRateGate(tokens_per_minute=10_000)
    started = time.monotonic()
    for _ in range(5):
        gate.acquire(1_000)
    assert time.monotonic() - started < 0.5


def test_gate_pause_holds_new_requests() -> None:
    gate = FoundryRateGate(tokens_per_minute=10_000)
    gate.pause(0.3)
    started = time.monotonic()
    gate.acquire(10)
    assert time.monotonic() - started >= 0.25


def test_revise_record_retries_rate_limit_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(semantic_qa_service.time, "sleep", lambda _seconds: None)
    provider = FakeProvider(failures=2)
    service = SemanticQAService(provider, FoundryRateGate(600_000))  # type: ignore[arg-type]
    revision = _revise(service)
    assert provider.calls == 3
    assert revision.goal.changed and revision.goal.text == "nieuw doel"
    assert not revision.description.changed
    assert service.input_tokens == 100 and service.output_tokens == 40


def test_revise_record_raises_after_max_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(semantic_qa_service.time, "sleep", lambda _seconds: None)
    provider = FakeProvider(failures=10)
    service = SemanticQAService(provider, FoundryRateGate(600_000))  # type: ignore[arg-type]
    with pytest.raises(FoundryProviderError):
        _revise(service)
    assert provider.calls == 5


def test_parallel_calls_count_usage_once_per_request() -> None:
    provider = FakeProvider()
    service = SemanticQAService(provider, FoundryRateGate(600_000))  # type: ignore[arg-type]
    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(lambda _i: _revise(service), range(200)))
    assert len(results) == 200
    assert provider.calls == 200
    assert service.input_tokens == 200 * 100
    assert service.output_tokens == 200 * 40
