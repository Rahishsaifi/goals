from fastapi.testclient import TestClient

from tests.conftest import login


def test_tenant_b_cannot_read_tenant_a_job_profiles(client: TestClient, two_tenants) -> None:
    assert login(client, "admin-a@example.com", "PasswordA-12345", "tenant-a").status_code == 200
    csrf = client.cookies.get("ri_csrf")
    created = client.post(
        "/api/v1/job-profiles",
        json={"title": "Backend Engineer", "source_text": "Need Python FastAPI"},
        headers={"x-csrf-token": csrf or ""},
    )
    assert created.status_code == 200
    profile_id = created.json()["id"]

    client.cookies.clear()
    assert login(client, "admin-b@example.com", "PasswordB-12345", "tenant-b").status_code == 200
    response = client.get(f"/api/v1/job-profiles/{profile_id}")
    assert response.status_code == 404


def test_forged_evaluation_id_is_tenant_scoped(client: TestClient, two_tenants) -> None:
    del two_tenants
    assert login(client, "admin-a@example.com", "PasswordA-12345", "tenant-a").status_code == 200
    csrf = client.cookies.get("ri_csrf")
    profile = client.post(
        "/api/v1/job-profiles",
        json={"title": "Role", "criteria": [
            {"key": "technical_skills", "weight": 100, "mandatory": True, "display_name": "Skills"}
        ]},
        headers={"x-csrf-token": csrf or ""},
    )
    assert profile.status_code == 200
    version_id = profile.json()["current_version_id"]
    run = client.post(
        "/api/v1/evaluations",
        json={"job_profile_version_id": version_id},
        headers={"x-csrf-token": csrf or ""},
    )
    assert run.status_code == 200
    run_id = run.json()["id"]

    client.cookies.clear()
    assert login(client, "admin-b@example.com", "PasswordB-12345", "tenant-b").status_code == 200
    assert client.get(f"/api/v1/evaluations/{run_id}").status_code == 404
    assert client.get(f"/api/v1/evaluations/{run_id}/results").status_code == 404
    csrf_b = client.cookies.get("ri_csrf")
    assert (
        client.delete(
            f"/api/v1/evaluations/{run_id}",
            headers={"x-csrf-token": csrf_b or ""},
        ).status_code
        == 404
    )


def test_owner_can_delete_evaluation_run(client: TestClient, two_tenants) -> None:
    del two_tenants
    assert login(client, "admin-a@example.com", "PasswordA-12345", "tenant-a").status_code == 200
    csrf = client.cookies.get("ri_csrf")
    profile = client.post(
        "/api/v1/job-profiles",
        json={
            "title": "Role",
            "criteria": [
                {
                    "key": "technical_skills",
                    "weight": 100,
                    "mandatory": True,
                    "display_name": "Skills",
                }
            ],
        },
        headers={"x-csrf-token": csrf or ""},
    )
    assert profile.status_code == 200
    run = client.post(
        "/api/v1/evaluations",
        json={"job_profile_version_id": profile.json()["current_version_id"]},
        headers={"x-csrf-token": csrf or ""},
    )
    assert run.status_code == 200
    run_id = run.json()["id"]
    deleted = client.delete(
        f"/api/v1/evaluations/{run_id}",
        headers={"x-csrf-token": csrf or ""},
    )
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "deleted"
    assert client.get(f"/api/v1/evaluations/{run_id}").status_code == 404
    listed = client.get("/api/v1/evaluations")
    assert listed.status_code == 200
    assert run_id not in {item["id"] for item in listed.json()}
