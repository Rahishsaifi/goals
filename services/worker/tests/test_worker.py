from worker.main import WorkerSettings


def test_worker_defaults_to_mock_provider() -> None:
    settings = WorkerSettings()
    assert settings.model_provider == "mock"
