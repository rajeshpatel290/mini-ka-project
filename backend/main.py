"""FastAPI backend for the digital evidence integrity demo."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone
from io import BytesIO

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from src import config
from src.case_id import CaseIdGenerationError, generate_case_id
from src.db import EvidenceRecord, SupabaseConfigError, SupabaseRepositoryError, get_repository


app = FastAPI(title="Digital Evidence Integrity API", version="1.0.0")

cors_origins = [
    "http://localhost:5173",
    "https://blockchain-eta-taupe.vercel.app",
    "https://mini-ka-project.vercel.app",
]
if config.FRONTEND_URL:
    cors_origins.append(config.FRONTEND_URL)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_origin_regex=r"https://.*\.vercel\.app",
    expose_headers=["X-Original-Hash", "X-Tampered-Hash", "X-Original-Filename", "Content-Disposition"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"detail": f"{type(exc).__name__}: {exc}"},
    )


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def repository_dependency():
    try:
        return get_repository()
    except SupabaseConfigError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except SupabaseRepositoryError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def read_upload(file: UploadFile) -> bytes:
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file must not be empty")
    return content


def filename_for(file: UploadFile) -> str:
    return file.filename or "evidence.bin"


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "backend": "supabase",
        "app_version": "cors-vercel-mini-2026-04-20",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/evidence/register")
async def register_evidence(
    file: UploadFile = File(...),
    case_name: str = Form(...),
    repository=Depends(repository_dependency),
) -> dict[str, str | None]:
    content = await read_upload(file)
    file_hash = sha256_bytes(content)
    try:
        case_id = generate_case_id(case_name, repository)
        record = repository.insert(
            EvidenceRecord(
                case_id=case_id,
                file_hash=file_hash,
                original_filename=filename_for(file),
            )
        )
    except CaseIdGenerationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except SupabaseRepositoryError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "case_id": record.case_id,
        "file_hash": record.file_hash,
        "original_filename": record.original_filename,
        "timestamp": record.timestamp,
        "message": "Evidence registered. Save your case_id to verify later.",
    }


@app.post("/evidence/verify")
async def verify_evidence(
    file: UploadFile = File(...),
    case_id: str = Form(...),
    repository=Depends(repository_dependency),
) -> dict[str, str | None]:
    record = repository.fetch(case_id)
    if record is None:
        raise HTTPException(status_code=404, detail="case_id not found")

    content = await read_upload(file)
    submitted_hash = sha256_bytes(content)
    status = "INTACT" if submitted_hash == record.file_hash else "TAMPERED"
    return {
        "case_id": record.case_id,
        "status": status,
        "submitted_hash": submitted_hash,
        "stored_hash": record.file_hash,
        "original_filename": record.original_filename,
        "registered_at": record.timestamp,
    }


@app.post("/evidence/tamper")
async def tamper_evidence(file: UploadFile = File(...)) -> StreamingResponse:
    content = await read_upload(file)
    original_hash = sha256_bytes(content)
    corrupted = content + secrets.token_bytes(secrets.randbelow(9) + 8)
    tampered_hash = sha256_bytes(corrupted)
    original_filename = filename_for(file)
    download_name = f"tampered_{original_filename}"

    response = StreamingResponse(BytesIO(corrupted), media_type=file.content_type or "application/octet-stream")
    response.headers["X-Original-Hash"] = original_hash
    response.headers["X-Tampered-Hash"] = tampered_hash
    response.headers["X-Original-Filename"] = original_filename
    response.headers["Content-Disposition"] = f'attachment; filename="{download_name.replace(chr(34), "")}"'
    return response


@app.get("/evidence/list")
def list_evidence(repository=Depends(repository_dependency)) -> dict[str, object]:
    try:
        records = repository.list_records()
    except SupabaseRepositoryError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    items = [
        {
            "case_id": record.case_id,
            "original_filename": record.original_filename,
            "timestamp": record.timestamp,
        }
        for record in records
    ]
    return {"total": len(items), "records": items}


@app.get("/evidence/{case_id}")
def get_evidence(case_id: str, repository=Depends(repository_dependency)) -> dict[str, str | None]:
    try:
        record = repository.fetch(case_id)
    except SupabaseRepositoryError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="case_id not found")
    return record.to_api_dict()
