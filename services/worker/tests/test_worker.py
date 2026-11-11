import pytest

from worker.main import WorkerSettings


def test_worker_defaults_to_mock_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MODEL_PROVIDER", raising=False)
    settings = WorkerSettings(_env_file=None)  # type: ignore[call-arg]
    assert settings.model_provider == "mock"
