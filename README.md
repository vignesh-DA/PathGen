# 🛠️ PathGen — Automated Test Case Generation System

![Python](https://img.shields.io/badge/Python-3.9+-blue.svg?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-009688.svg?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18+-61DAFB.svg?logo=react&logoColor=black)
![Z3](https://img.shields.io/badge/Z3_Solver-Theorem_Proving-critical.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)

> **Compiler-Design Capstone Project** — Deterministically derives test cases from real C program structure using `pycparser` (AST) + `networkx` (CFG) + `Z3` symbolic solving. AI (Groq/LangChain) is used *exclusively* for plain-English explanations, ensuring test case derivation remains strictly mathematical and sound.

---

## ✨ Key Features

- 🔍 **Real C Parsing**: Leverages `pycparser` AST with a fake-libc stub—no GCC required.
- ⬡ **Interactive Control Flow Graphs (CFG)**: Uses `networkx` + `react-flow` for beautiful, interactive, color-coded graphs.
- ⚡ **Z3 Symbolic Solving**: Computes `TRUE`, `FALSE`, and critical boundary values mathematically for every condition.
- ✓ **Deterministic Accuracy**: Canonical test cases (e.g., `age >= 18`) produce exact, expected mathematical boundaries.
- 🤖 **Bounded AI Explanations**: Uses Groq LLMs purely as a post-processing step to generate human-readable explanations of execution paths.
- 📊 **Robust Exporting**: Download your generated test suites instantly in JSON or CSV format.
- 🗄️ **Persistent Run History**: Uses SQLite-persisted session data to keep track of previous analyses.

---

## 🏗️ Architecture & Tech Stack

| Component | Technology |
|---|---|
| **Syntax Parsing** | `pycparser` |
| **Graph Modeling (CFG)** | `networkx` |
| **Constraint & Symbolic Solving** | `z3-solver` |
| **Backend Framework** | `FastAPI` + `Pydantic v2` |
| **LLM / AI Layer** | `LangChain` + `Groq` (`llama-3.3-70b-versatile`) |
| **Frontend Framework** | `React` + `Vite` |
| **Code Editor** | `Monaco Editor` |
| **Graph Visualization** | `react-flow` |
| **Database & Storage** | `SQLite` + `SQLAlchemy` |
| **Testing Suite** | `pytest` |

---

## 🚀 Quick Start Guide

### 1. Backend Setup

First, navigate to the backend directory and set up the environment:

```bash
cd backend

# Install all required Python dependencies
pip install -r requirements.txt

# Configure your environment variables
cp .env.example .env
```
*Note: Ensure you edit `.env` and set `GROQ_API_KEY=gsk_...` with your actual Groq API key.*

Start the development server:
```bash
uvicorn app.main:app --reload --port 8000
```
📚 **API Documentation**: Open [http://localhost:8000/docs](http://localhost:8000/docs) for the interactive Swagger UI.

### 2. Frontend Setup

In a new terminal, launch the React interface:

```bash
cd frontend
npm install
npm run dev
```
🌐 **Web App**: Open [http://localhost:5173](http://localhost:5173) in your browser.

### 3. Running the Test Suite

Validate the system core using the provided tests:

```bash
cd backend
python -m pytest tests/ -v
```

---

## 💡 How to Use PathGen

1. **Input Code**: Paste your C source code into the embedded Monaco editor (or use the provided `age >= 18` default template).
2. **Target Function**: Specify the name of the function you wish to analyze (default: `classify_age`).
3. **Generate CFG**: Click **▶ Analyze**. The CFG will dynamically render with color-coded execution edges:
   - 🟢 **Green** = TRUE branch
   - 🔴 **Red** = FALSE branch
   - 🟡 **Gold** = Back-edge (Loop)
   - 🔵 **Blue** = Sequential execution
4. **Solve Paths**: Click **⚡ Generate Tests** to populate the test case table based on symbolic execution.
5. **Insights**: Click on any generated test case row to slide in the explanation panel featuring:
   - A plain-English AI-generated explanation.
   - The path decisions made (`TRUE`/`FALSE` per condition).
   - Step-by-step execution path tracking.
6. **Export**: Export your complete test suite to JSON or CSV via the **↓ JSON** or **↓ CSV** buttons.

---

## 📂 Project Structure

```text
pathgen/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI entrypoint
│   │   ├── config.py                # Pydantic settings configuration
│   │   ├── api/                     # REST Route handlers
│   │   ├── core/                    # Core compiler analysis modules
│   │   │   ├── ast_parser.py        # pycparser wrapper
│   │   │   ├── cfg_builder.py       # networkx CFG construction
│   │   │   ├── condition_extractor.py
│   │   │   ├── symbolic_solver.py   # Z3 Theorem Prover integration
│   │   │   ├── path_enumerator.py   # DFS path enumeration
│   │   │   └── test_case_builder.py
│   │   ├── ai/                      # Bounded LangChain + Groq integration
│   │   ├── models/                  # Pydantic + SQLAlchemy data models
│   │   └── db/                      # SQLite database sessions
│   ├── tests/
│   │   └── sample_programs/         # Benchmark C programs for validation
│   └── requirements.txt
└── frontend/
    ├── src/
    │   ├── components/              # UI Components (Monaco, react-flow, etc.)
    │   ├── pages/Home.jsx
    │   └── api/client.js
    └── vite.config.js
```

---

## ⚙️ Environment Configuration

| Variable | Description | Default Value |
|---|---|---|
| `GROQ_API_KEY` | Your Groq API key from console.groq.com | *(Required)* |
| `GROQ_MODEL` | LLM model for explanations | `llama-3.3-70b-versatile` |
| `DATABASE_URL` | SQLite connection string | `sqlite:///./pathgen.db` |
| `MAX_PATHS` | Cap for CFG path enumeration | `50` |
| `MAX_LOOP_ITERATIONS` | Maximum loop unrolling depth | `3` |

---

## 🧪 Canonical End-to-End Validation

For the standard `age >= 18` control flow, PathGen's Z3 solver guarantees the following exact outputs:

| ID | Input | Branch | Expected Output | Boundary Value? |
|---|---|---|---|:---:|
| **TC01** | `age = 20` | `TRUE` | Adult | No |
| **TC02** | `age = 17` | `FALSE` | Minor | No |
| **TC03** | `age = 18` | `TRUE` | Adult | **Yes** |

*(Validate this automatically by running `pytest tests/test_symbolic_solver.py -v`)*

---

## 🔌 Core API Endpoints

| Method | Endpoint | Description |
|:---:|---|---|
| **POST** | `/api/analyze` | Parses C code and returns the CFG JSON + conditions. |
| **POST** | `/api/generate-tests` | Runs the full pipeline returning test cases + solver metadata. |
| **GET** | `/api/history` | Fetches a paginated list of past analysis runs. |
| **GET** | `/api/history/{id}` | Fetches full details for a specific historical run. |
