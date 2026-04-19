"""Supabase repository used by the FastAPI backend."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import config


class SupabaseConfigError(RuntimeError):
    """Raised when Supabase credentials are missing or invalid."""


class SupabaseRepositoryError(RuntimeError):
    """Raised when a Supabase operation fails."""


@dataclass(frozen=True)
class EvidenceRecord:
    case_id: str
    file_hash: str
    original_filename: str
    timestamp: str | None = None
    submitter: str = "demo-user"

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "EvidenceRecord":
        return cls(
            case_id=row["case_id"],
            file_hash=row["file_hash"],
            original_filename=row["original_filename"],
            timestamp=row.get("timestamp"),
            submitter=row.get("submitter") or "demo-user",
        )

    def to_insert_payload(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "file_hash": self.file_hash,
            "original_filename": self.original_filename,
            "submitter": self.submitter,
        }

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "file_hash": self.file_hash,
            "original_filename": self.original_filename,
            "timestamp": self.timestamp,
            "submitter": self.submitter,
        }


class SupabaseEvidenceRepository:
    def __init__(self, url: str = config.SUPABASE_URL, key: str = config.SUPABASE_KEY) -> None:
        if not url or not key:
            raise SupabaseConfigError("SUPABASE_URL and SUPABASE_KEY must be set")
        try:
            from supabase import create_client
        except ImportError as exc:
            raise SupabaseConfigError("Install supabase first: pip install -r requirements.txt") from exc

        try:
            self.client = create_client(url, key)
        except Exception as exc:
            raise SupabaseConfigError(f"Supabase client initialization failed: {exc}") from exc

    def exists(self, case_id: str) -> bool:
        return self.fetch(case_id) is not None

    def insert(self, record: EvidenceRecord) -> EvidenceRecord:
        try:
            result = (
                self.client.table("records")
                .insert(record.to_insert_payload())
                .execute()
            )
        except Exception as exc:
            raise SupabaseRepositoryError(f"Supabase insert failed: {exc}") from exc
        rows = _extract_rows(result)
        if not rows:
            raise SupabaseRepositoryError("Supabase insert returned no record")
        return EvidenceRecord.from_row(rows[0])

    def fetch(self, case_id: str) -> EvidenceRecord | None:
        try:
            result = (
                self.client.table("records")
                .select("*")
                .eq("case_id", case_id)
                .limit(1)
                .execute()
            )
        except Exception as exc:
            raise SupabaseRepositoryError(f"Supabase fetch failed: {exc}") from exc
        rows = _extract_rows(result)
        if not rows:
            return None
        return EvidenceRecord.from_row(rows[0])

    def list_records(self) -> list[EvidenceRecord]:
        try:
            result = (
                self.client.table("records")
                .select("case_id, original_filename, timestamp, file_hash, submitter")
                .order("timestamp", desc=True)
                .execute()
            )
        except Exception as exc:
            raise SupabaseRepositoryError(f"Supabase list failed: {exc}") from exc
        return [EvidenceRecord.from_row(row) for row in _extract_rows(result)]


def _extract_rows(result: Any) -> list[dict[str, Any]]:
    rows = getattr(result, "data", None)
    if rows is None and isinstance(result, dict):
        rows = result.get("data")
    if rows is None:
        return []
    if not isinstance(rows, list):
        raise SupabaseRepositoryError("Supabase response data was not a list")
    return rows


_repository: SupabaseEvidenceRepository | None = None


def get_repository() -> SupabaseEvidenceRepository:
    global _repository
    if _repository is None:
        _repository = SupabaseEvidenceRepository()
    return _repository


def reset_repository_cache() -> None:
    global _repository
    _repository = None
