# Blockchain-Based Digital Evidence Integrity System

Working CLI prototype for the CSE 435 seminar topic: ensuring digital evidence integrity with SHA-256 fingerprints, off-chain evidence storage, and an immutable ledger record.

The prototype supports two ledger backends behind the same interface:

- SQLite fallback, which works offline and is used automatically when Ganache is not configured.
- Ganache + Solidity, using `backend/contracts/EvidenceLedger.sol` for a local Ethereum demo.
- FastAPI + Supabase backend for a deployable web/API demo.

## Project Layout

```text
D:\mini
├── backend\              # FastAPI backend, CLI demo, tests, Python requirements
│   ├── main.py
│   ├── requirements.txt
│   ├── src\
│   ├── scripts\
│   ├── tests\
│   └── .env              # local backend secrets, gitignored
├── frontend\
│   └── index.html        # static frontend, no build step
└── README.md
```

## Quickstart

Put or paste your evidence content into `backend\evidence`.

```powershell
cd D:\mini\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pytest
python scripts/demo.py
```

The demo runs the seven-step mechanism:

1. collect evidence from `evidence`
2. generate a SHA-256 hash
3. store the hash in the active ledger backend
4. copy the original file into `evidence_vault/`
5. re-hash the vaulted evidence
6. confirm the evidence is intact
7. append bytes to the vaulted file and detect tampering

## FastAPI Backend

Create this table in Supabase:

```sql
CREATE TABLE records (
    case_id           TEXT PRIMARY KEY,
    file_hash         TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    timestamp         TIMESTAMPTZ DEFAULT NOW(),
    submitter         TEXT DEFAULT 'demo-user'
);
```

Create a local backend `.env` file at `backend\.env`:

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-supabase-key
FRONTEND_URL=http://localhost:5173
```

Run the API:

```powershell
cd D:\mini\backend
uvicorn main:app --reload
```

Open the API docs:

```text
http://127.0.0.1:8000/docs
```

API endpoints:

- `GET /health`
- `POST /evidence/register` with multipart `file` and `case_name`
- `POST /evidence/verify` with multipart `file` and `case_id`
- `POST /evidence/tamper` with multipart `file`
- `GET /evidence/list`
- `GET /evidence/{case_id}`

The API stores only hashes and metadata in Supabase. Uploaded files are not permanently stored. Register and verify hash uploaded files in chunks, so images and larger evidence files do not need to be loaded fully into memory.

## Static Frontend

Open `frontend\index.html` directly in your browser after the API is running:

```text
D:\mini\frontend\index.html
```

The frontend uses this backend URL at the top of its script:

```js
const API_URL = "https://startup-suggest-name-1.onrender.com";
```

For local-only testing, temporarily change that value to `http://localhost:8000`. You can deploy the frontend by dragging `frontend\index.html` into Vercel.

Example API flow with PowerShell:

```powershell
$register = Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/evidence/register" `
  -Method Post `
  -Form @{ case_name = "demo case"; file = Get-Item "D:\mini\backend\evidence" }

$register.case_id

Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/evidence/verify" `
  -Method Post `
  -Form @{ case_id = $register.case_id; file = Get-Item "D:\mini\backend\evidence" }
```

## Useful Commands

Hash a file:

```powershell
cd D:\mini\backend
python -m src.hash_evidence
```

Store a record:

```powershell
cd D:\mini\backend
python -m src.store_record CASE-001 --backend sqlite
```

Verify the vaulted evidence:

```powershell
cd D:\mini\backend
python -m src.verify_evidence CASE-001 --backend sqlite
```

Simulate tampering:

```powershell
cd D:\mini\backend
python -m src.simulate_tampering CASE-001 --backend sqlite
```

`verify_evidence` exits with:

- `0` when evidence is intact
- `2` when tampering is detected
- `1` when no ledger record exists

## Ganache Mode

Start Ganache on `http://127.0.0.1:7545`, then deploy the contract:

```powershell
cd D:\mini\backend
python scripts/deploy_contract.py
```

Set the printed contract address for the current terminal:

```powershell
$env:EVIDENCE_CONTRACT_ADDRESS = "0x..."
$env:EVIDENCE_BACKEND = "web3"
python scripts/demo.py
```

If Ganache, Web3.py, or the contract address is unavailable and `EVIDENCE_BACKEND` is `auto`, the prototype transparently falls back to SQLite.

## Environment Variables

- `EVIDENCE_BACKEND`: `auto`, `sqlite`, or `web3`
- `EVIDENCE_FILE`: custom default evidence file path, default `./evidence`
- `EVIDENCE_SQLITE_PATH`: custom SQLite ledger path
- `EVIDENCE_VAULT`: custom off-chain vault directory
- `GANACHE_URL`: local Ethereum RPC URL, default `http://127.0.0.1:7545`
- `EVIDENCE_CONTRACT_ADDRESS`: deployed `EvidenceLedger` address for Web3 mode
- `SUPABASE_URL`: Supabase project URL for the FastAPI backend
- `SUPABASE_KEY`: Supabase API key for the FastAPI backend
- `FRONTEND_URL`: deployed frontend origin for CORS

## Render Deployment

Set Render **Root Directory** to:

```text
backend
```

Backend build command:

```powershell
pip install -r requirements.txt
```

Backend start command:

```powershell
uvicorn main:app --host 0.0.0.0 --port $PORT
```

Set these Render environment variables:

```text
SUPABASE_URL
SUPABASE_KEY
FRONTEND_URL
```

Set `FRONTEND_URL` to your Vercel frontend URL, for example:

```text
https://mini-ka-project.vercel.app
```

Use the Supabase API key format supported by your Supabase project/client version, then redeploy Render after saving environment variable changes.

## Scope Notes

This is a seminar prototype, not a production evidence system. It intentionally excludes authentication, role-based access control, IPFS/S3 storage, legal compliance workflows, and zero-knowledge proofs. The CLI local vault is plaintext; `src/vault.py` marks AES-GCM encryption as future work.
