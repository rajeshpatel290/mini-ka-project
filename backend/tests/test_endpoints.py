from dataclasses import replace

from fastapi.testclient import TestClient

import main
from main import app, repository_dependency, sha256_bytes
from src.db import EvidenceRecord, SupabaseConfigError


class FakeRepository:
    def __init__(self) -> None:
        self.records: dict[str, EvidenceRecord] = {}
        self.candidate_exists = False

    def exists(self, case_id: str) -> bool:
        return self.candidate_exists or case_id in self.records

    def insert(self, record: EvidenceRecord) -> EvidenceRecord:
        stored = replace(record, timestamp="2026-04-19T10:30:00Z")
        self.records[stored.case_id] = stored
        return stored

    def fetch(self, case_id: str) -> EvidenceRecord | None:
        return self.records.get(case_id)

    def list_records(self) -> list[EvidenceRecord]:
        return list(self.records.values())


def client_with(repository: FakeRepository) -> TestClient:
    app.dependency_overrides[repository_dependency] = lambda: repository
    return TestClient(app)


def clear_overrides() -> None:
    app.dependency_overrides.clear()


def test_health() -> None:
    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["backend"] == "supabase"


def test_vercel_origin_is_allowed_by_cors() -> None:
    client = TestClient(app)

    for origin in [
        "https://blockchain-eta-taupe.vercel.app",
        "https://mini-ka-project.vercel.app",
    ]:
        response = client.options(
            "/evidence/register",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == origin


def test_register_returns_generated_case_id_and_metadata() -> None:
    repository = FakeRepository()
    client = client_with(repository)

    response = client.post(
        "/evidence/register",
        data={"case_name": "Cyber Fraud Case"},
        files={"file": ("email.eml", b"original evidence", "message/rfc822")},
    )
    clear_overrides()

    body = response.json()
    assert response.status_code == 200
    assert body["case_id"].startswith("cyber-fraud-case-")
    assert body["file_hash"] == sha256_bytes(b"original evidence")
    assert body["original_filename"] == "email.eml"
    assert body["timestamp"] == "2026-04-19T10:30:00Z"
    assert body["case_id"] in repository.records


def test_verify_returns_intact_for_matching_file() -> None:
    repository = FakeRepository()
    file_hash = sha256_bytes(b"original evidence")
    repository.records["case-123"] = EvidenceRecord(
        case_id="case-123",
        file_hash=file_hash,
        original_filename="email.eml",
        timestamp="2026-04-19T10:30:00Z",
    )
    client = client_with(repository)

    response = client.post(
        "/evidence/verify",
        data={"case_id": "case-123"},
        files={"file": ("email.eml", b"original evidence", "message/rfc822")},
    )
    clear_overrides()

    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "INTACT"
    assert body["submitted_hash"] == body["stored_hash"]


def test_verify_returns_tampered_for_changed_file() -> None:
    repository = FakeRepository()
    repository.records["case-123"] = EvidenceRecord(
        case_id="case-123",
        file_hash=sha256_bytes(b"original evidence"),
        original_filename="email.eml",
        timestamp="2026-04-19T10:30:00Z",
    )
    client = client_with(repository)

    response = client.post(
        "/evidence/verify",
        data={"case_id": "case-123"},
        files={"file": ("email.eml", b"changed evidence", "message/rfc822")},
    )
    clear_overrides()

    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "TAMPERED"
    assert body["submitted_hash"] != body["stored_hash"]


def test_verify_and_fetch_unknown_case_return_404() -> None:
    repository = FakeRepository()
    client = client_with(repository)

    verify_response = client.post(
        "/evidence/verify",
        data={"case_id": "missing-case"},
        files={"file": ("email.eml", b"original evidence", "message/rfc822")},
    )
    fetch_response = client.get("/evidence/missing-case")
    clear_overrides()

    assert verify_response.status_code == 404
    assert fetch_response.status_code == 404


def test_list_returns_total_and_records() -> None:
    repository = FakeRepository()
    repository.records["case-123"] = EvidenceRecord(
        case_id="case-123",
        file_hash=sha256_bytes(b"original evidence"),
        original_filename="email.eml",
        timestamp="2026-04-19T10:30:00Z",
    )
    client = client_with(repository)

    response = client.get("/evidence/list")
    clear_overrides()

    body = response.json()
    assert response.status_code == 200
    assert body["total"] == 1
    assert body["records"] == [
        {
            "case_id": "case-123",
            "original_filename": "email.eml",
            "timestamp": "2026-04-19T10:30:00Z",
        }
    ]


def test_tamper_returns_corrupted_download_with_hash_headers() -> None:
    client = TestClient(app)

    response = client.post(
        "/evidence/tamper",
        files={"file": ("email.eml", b"original evidence", "message/rfc822")},
    )

    assert response.status_code == 200
    assert response.content.startswith(b"original evidence")
    assert response.content != b"original evidence"
    assert response.headers["X-Original-Hash"] == sha256_bytes(b"original evidence")
    assert response.headers["X-Tampered-Hash"] == sha256_bytes(response.content)
    assert response.headers["X-Original-Filename"] == "email.eml"
    assert response.headers["Content-Disposition"] == 'attachment; filename="tampered_email.eml"'


def test_register_without_supabase_env_returns_clear_500(monkeypatch) -> None:
    app.dependency_overrides.clear()
    monkeypatch.setattr(
        main,
        "get_repository",
        lambda: (_ for _ in ()).throw(SupabaseConfigError("SUPABASE_URL and SUPABASE_KEY must be set")),
    )
    client = TestClient(app)

    response = client.post(
        "/evidence/register",
        data={"case_name": "Cyber Fraud Case"},
        files={"file": ("email.eml", b"original evidence", "message/rfc822")},
    )

    assert response.status_code == 500
    assert "SUPABASE_URL and SUPABASE_KEY must be set" in response.json()["detail"]
