from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.integrations.foundry_provider import FoundryProviderError
from app.services.goals_localization.semantic_qa_service import SemanticQAService


class _FakeProvider:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls = 0

    def _chat_json(self, *, system: str, user: str) -> dict[str, object]:
        self.calls += 1
        assert "untranslated_phrases" in user
        return {
            "json": self.payload,
            "usage": SimpleNamespace(input_tokens=10, output_tokens=5),
        }


def test_rework_residual_english_returns_corrected_text() -> None:
    provider = _FakeProvider(
        {
            "field": "description",
            "corrected_text": "Begeleid het maritieme reis-ondersteuningsteam.",
            "notes": "Translated Marine travel support team",
        }
    )
    service = SemanticQAService(provider)  # type: ignore[arg-type]

    result = service.rework_residual_english(
        field="description",
        target_language="nl",
        source_text="guide the Marine travel support team",
        translated_text="begeleid het Marine travel support team",
        untranslated_phrases=["Marine travel support team"],
        preserve_terms=["BCD"],
    )

    assert result.corrected_text.startswith("Begeleid")
    assert "Marine travel support team" not in result.corrected_text
    assert provider.calls == 1
    assert service.input_tokens == 10


def test_rework_residual_english_rejects_empty_text() -> None:
    provider = _FakeProvider({"field": "goal", "corrected_text": "  ", "notes": ""})
    service = SemanticQAService(provider)  # type: ignore[arg-type]

    with pytest.raises(FoundryProviderError, match="empty corrected_text"):
        service.rework_residual_english(
            field="goal",
            target_language="nl",
            source_text="Lead delivery",
            translated_text="Lead delivery",
            untranslated_phrases=["Lead delivery"],
            preserve_terms=[],
        )
