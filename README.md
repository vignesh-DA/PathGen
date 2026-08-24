# PathGen — Automated Test Case Generation System

> **Compiler-Design Capstone Project** — Derives test cases deterministically from real C program structure using pycparser (AST) + networkx (CFG) + Z3 symbolic solving. AI (Groq/LangChain) is used *only* for plain-English explanations, never for deciding what the test cases are.

## Features

- 🔍 **Real C Parsing** — pycparser AST with fake-libc stub (no gcc needed)
- ⬡ **Interactive CFG** — networkx + react-flow with colour-coded edges
- ⚡ **Z3 Symbolic Solving** — TRUE / FALSE / boundary values per condition
- ✓ **TC01/TC02/TC03** — canonical age ≥ 18 example produces exact expected output
- 🤖 **Bounded AI** — Groq explanations as post-processing only
- 📊 **Export** — JSON & CSV download
- 🗄️ **History** — SQLite-persisted run history

## Tech Stack

| Layer | Technology |
|---|---|
| Parsing | `pycparser` |
| CFG | `networkx` |
| Symbolic solving | `z3-solver` |
| Backend | `FastAPI` + `Pydantic v2` |
| AI | `LangChain` + `Groq` (`llama-3.3-70b-versatile`) |
| Frontend | `React` + `Vite` |
| Code editor | `Monaco Editor` |
| CFG visualisation | `react-flow` |
| Storage | `SQLite` + `SQLAlchemy` |
| Testing | `pytest` |

## Quick Start

### 1. Backend

```bash
cd backend

# Install dependencies (system Python or venv)
pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env
# Edit .env → set GROQ_API_KEY=gsk_...

# Run development server
uvicorn app.main:app --reload --port 8000
```

Open Swagger UI: http://localhost:8000/docs

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open: http://localhost:5173

### 3. Run Tests

```bash
cd backend
python -m pytest tests/ -v
```

## Usage

1. Paste C source code into the Monaco editor (or use the default `age >= 18` example)
2. Enter the function name to analyse (default: `classify_age`)
3. Click **▶ Analyze** → CFG appears with colour-coded edges:
   - 🟢 Green = TRUE branch
   - 🔴 Red = FALSE branch
   - 🟡 Gold = back-edge (loop)
   - 🔵 Blue = sequential
4. Click **⚡ Generate Tests** → test case table appears
5. Click any row → explanation panel slides in with:
   - AI-generated plain-English explanation
   - Path decisions (TRUE/FALSE per condition)
   - Execution path steps
6. Click **↓ JSON** or **↓ CSV** to export

## Folder Structure

```
pathgen/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI entrypoint
│   │   ├── config.py                # pydantic-settings
│   │   ├── api/                     # Route handlers
│   │   ├── core/                    # Compiler analysis modules
│   │   │   ├── ast_parser.py        # pycparser wrapper
│   │   │   ├── cfg_builder.py       # networkx CFG
│   │   │   ├── condition_extractor.py
│   │   │   ├── symbolic_solver.py   # z3-solver
│   │   │   ├── path_enumerator.py   # DFS path enumeration
│   │   │   └── test_case_builder.py
│   │   ├── ai/                      # LangChain + Groq (bounded)
│   │   ├── models/                  # Pydantic + SQLAlchemy models
│   │   └── db/                      # SQLite session
│   ├── tests/
│   │   └── sample_programs/         # C programs for validation
│   ├── memory.md                    # Architecture decisions log
│   └── requirements.txt
└── frontend/
    ├── src/
    │   ├── components/              # CodeEditor, CFGViewer, TestCaseTable, ExplanationPanel
    │   ├── pages/Home.jsx
    │   └── api/client.js
    └── vite.config.js
```

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `GROQ_API_KEY` | Groq API key (console.groq.com) | *required* |
| `GROQ_MODEL` | Groq model name | `llama-3.3-70b-versatile` |
| `DATABASE_URL` | SQLite path | `sqlite:///./pathgen.db` |
| `MAX_PATHS` | Max CFG paths to enumerate | `50` |
| `MAX_LOOP_ITERATIONS` | Max loop unrolling depth | `3` |

## Canonical End-to-End Test

For the `age >= 18` example, the system must produce:

| ID | Input | Branch | Expected Output | Boundary? |
|---|---|---|---|---|
| TC01 | age = 20 | TRUE | Adult | No |
| TC02 | age = 17 | FALSE | Minor | No |
| TC03 | age = 18 | TRUE | Adult | **Yes** |

Run `pytest tests/test_symbolic_solver.py -v` to validate this automatically.

## API Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/api/analyze` | Parse C code → CFG JSON + conditions |
| POST | `/api/generate-tests` | Full pipeline → test cases + solver metadata |
| GET | `/api/history` | Paginated list of past runs |
| GET | `/api/history/{id}` | Full detail for one run |

Full docs at `/docs` (Swagger UI) when the backend is running.
