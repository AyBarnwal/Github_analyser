# DevLens — GitHub Candidate Intelligence Platform

> AI-powered technical candidate evaluation using a 5-phase RAG pipeline, AST-based code analysis, and a local LLM scorer.

---

## Table of Contents

- [Overview](#overview)
- [System Architecture](#system-architecture)
- [Pipeline Phases](#pipeline-phases)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running the App](#running-the-app)
- [How Scoring Works](#how-scoring-works)
- [Customising the Rubric](#customising-the-rubric)
- [Reliability Notes](#reliability-notes)
- [Troubleshooting](#troubleshooting)
- [Tech Stack](#tech-stack)

---

## Overview

DevLens takes a GitHub username and runs it through a fully automated pipeline that:

1. Fetches merged pull requests and full source files from GitHub
2. Filters out noise (lock files, minified assets, auto-generated code)
3. Parses code structure with Tree-sitter to extract clean function/class definitions
4. Stores code chunks in a semantic vector store and retrieves the most relevant evidence per rubric dimension
5. Scores the candidate against an engineering rubric using a local LLM with chain-of-thought reasoning

The result is a structured JSON report with per-dimension scores (0–100), LLM rationale for each score, and a radar chart visualisation — all rendered in a dark, professional dashboard UI.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Frontend (React + Vite)                  │
│   Input: GitHub username  →  POST /api/analyze  →  Report UI    │
└─────────────────────────────────┬───────────────────────────────┘
                                  │ HTTP
┌─────────────────────────────────▼───────────────────────────────┐
│                       Backend (FastAPI)                          │
│                                                                  │
│   Phase 1 · INGEST     GitHub REST API → full file contents     │
│       ↓                                                          │
│   Phase 2 · PRUNE      Regex heuristics → drop noise files      │
│       ↓                                                          │
│   Phase 3 · ASSEMBLE   Tree-sitter AST → function/class chunks  │
│       ↓                                                          │
│   Phase 4 · EVALUATE   Per-dimension RAG → Ollama LLM (×3 avg) │
│       ↓                                                          │
│   Phase 5 · REPORT     JSON score matrix → FastAPI response     │
└─────────────────────────────────────────────────────────────────┘
```

---

## Pipeline Phases

### Phase 1 — Ingest
Connects to the GitHub REST API and collects code from two sources:
- **Merged pull requests** — finished, peer-reviewed work across up to 15 repos × 8 PRs each
- **Recent commits** — used as a fallback when the account has fewer than 6 PR files

For each file, the pipeline fetches the **complete file contents** (not just the diff hunk) via the `/contents` API. Files larger than 200 KB are skipped.

### Phase 2 — Prune
A fast O(n) regex filter discards files that carry no engineering signal:
lock files, minified assets, build artefacts, images, migration files, auto-generated protobuf files, and `.env` files.

### Phase 3 — Assemble
Tree-sitter parses each source file and extracts only complete **function and class definitions**. Comments and docstrings are stripped. Falls back to regex extraction for unsupported file types.

Supported languages: **Python**, **JavaScript**, **TypeScript**, **JSX**, **TSX**

### Phase 4 — Evaluate
The RAG scoring engine:
1. Stores all code chunks in an in-memory vector store (semantic embeddings via `nomic-embed-text`, with TF-IDF fallback)
2. Runs a **separate vector query per rubric dimension** to retrieve the most relevant evidence for each criterion
3. Calls the LLM **3 times per dimension** with a chain-of-thought prompt and averages the results
4. Returns scores (0–100) and a brief rationale string for each dimension

### Phase 5 — Report
Wraps the score matrix with pipeline metadata (repo count, file counts by source type) and returns a structured JSON response to the frontend.

---

## Project Structure

```
devlens/
├── backend/
│   ├── .env                  # Your secrets (not committed)
│   ├── main.py               # FastAPI app + /api/analyze endpoint
│   ├── pipeline.py           # 5-phase analysis pipeline
│   ├── rubric.json           # Scoring criteria (customisable)
│   ├── requirements.txt      # Python dependencies
│   └── venv/                 # Virtual environment
│
├── frontend/
│   ├── index.html            # Vite entry point + Google Fonts
│   ├── package.json
│   └── src/
│       ├── App.jsx           # Main UI — search, results, PDF export
│       ├── main.jsx          # React root mount
│       ├── index.css         # Dark terminal theme + Tailwind
│       └── components/
│           └── RadarChartComponent.jsx   # Recharts radar chart
│
└── README.md
```

---

## Prerequisites

| Tool | Version | Purpose |
|---|---|---|
| Python | 3.10 – 3.13 | Backend runtime |
| Node.js | 18+ | Frontend build |
| Ollama | Latest | Local LLM server |
| Git | Any | Cloning |

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/your-username/devlens.git
cd devlens
```

### 2. Set up the backend

```bash
cd backend
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
```

### 3. Set up the frontend

```bash
cd frontend
npm install
```

### 4. Install Ollama

Download from **https://ollama.com/download** and install it.

Then pull the required models:

```bash
# LLM scorer (required)
ollama pull llama3.2

# Embedding model (recommended — improves retrieval accuracy)
ollama pull nomic-embed-text
```

> **Note:** `nomic-embed-text` is ~270 MB. Without it the system falls back to TF-IDF keyword matching, which is less accurate but still functional.

---

## Configuration

Create `backend/.env` with the following:

```env
# Required — raises GitHub rate limit from 60 to 5,000 req/hr
GITHUB_TOKEN=ghp_your_token_here

# Optional — change the LLM model (default: llama3.2)
OLLAMA_MODEL=llama3.2

# Optional — change the embedding model (default: nomic-embed-text)
EMBED_MODEL=nomic-embed-text

# Optional — number of scoring runs per dimension, averaged (default: 3)
# Higher = more stable scores, slower analysis
SCORE_RUNS=3
```

### Getting a GitHub Token

1. Go to **https://github.com/settings/tokens**
2. Click **Generate new token (classic)**
3. Give it a name, set an expiry, and tick only **`public_repo`**
4. Copy the token and paste it into `.env`

---

## Running the App

Open **two terminals**:

**Terminal 1 — Backend**

```bash
cd backend
venv\Scripts\activate       # Windows
# source venv/bin/activate  # macOS / Linux
uvicorn main:app --reload --port 8000
```

**Terminal 2 — Frontend**

```bash
cd frontend
npm run dev
```

Open **http://localhost:5173** in your browser.

To verify the backend is running: visit **http://localhost:8000** — you should see:

```json
{
  "status": "ok",
  "github_token_configured": true,
  "warning": null
}
```

> **Every time you reboot**, you may need to start Ollama again. Check your system tray — the Ollama installer usually adds it to startup automatically on Windows.

---

## How Scoring Works

The rubric in `rubric.json` defines four dimensions for a **Backend Engineer** role:

| Dimension | What the LLM looks for |
|---|---|
| **Maintainability** | Clear variable names, modular functions, absence of deep nesting |
| **Framework Skill** | Proper async/await usage, RESTful patterns, standard library usage |
| **Error Handling** | Explicit try/except blocks, logging, no silent failures |
| **Algorithmic Efficiency** | Avoids O(n²) loops, uses appropriate data structures (sets, dicts) |

Each dimension is scored independently:
- The vector store retrieves the 12 code chunks most semantically relevant to that criterion
- The LLM is asked to reason about those chunks in 2–3 sentences before producing a score
- This is repeated 3 times and the scores are averaged to reduce LLM randomness
- Final scores are clamped to the range [0, 100]

The overall score displayed in the header is the average of all four dimension scores.

---

## Customising the Rubric

Edit `backend/rubric.json` to target any role. The pipeline adapts automatically — no code changes needed.

```json
{
  "role": "Frontend Engineer",
  "criteria": {
    "component_design":     "Proper separation of concerns, reusable components, props validation.",
    "state_management":     "Appropriate use of local vs global state, avoiding unnecessary re-renders.",
    "accessibility":        "Semantic HTML, ARIA attributes, keyboard navigability.",
    "performance":          "Lazy loading, memoisation, avoiding layout thrashing."
  }
}
```

---

## Reliability Notes

The system produces more reliable results when:

- The candidate has **active public repositories** with merged pull requests
- The `nomic-embed-text` embedding model is installed (semantic retrieval vs keyword matching)
- `SCORE_RUNS` is set to 5 or higher for more stable averaging
- A **GitHub token is configured** (more files fetched before hitting rate limits)

Scores are less reliable when:
- The account has few public repos or no merged PRs (pipeline falls back to recent commits)
- Files are primarily in languages other than Python or JavaScript/TypeScript
- Ollama is running on a machine with less than 8 GB of available RAM (model may crash mid-inference)

---

## Troubleshooting

**`Ollama unavailable` in scores**
Ollama is not running or the model is not pulled.
```bash
ollama serve          # start the server
ollama pull llama3.2  # pull the model if not done yet
```

**`llama runner process has terminated`**
Your machine does not have enough RAM to load the model. Switch to a smaller one:
```bash
ollama pull llama3.2:1b
# then set OLLAMA_MODEL=llama3.2:1b in backend/.env
```

**`GitHub API rate limit reached`**
You are running without a token. Add `GITHUB_TOKEN` to `backend/.env` and restart the backend.

**`Module not found: RadarChartComponent`**
The component file is missing. Ensure `frontend/src/components/RadarChartComponent.jsx` exists.

**`rubric.json not found`**
Always run `uvicorn` from inside the `backend/` directory, not from the repo root.

**Scores are 0 for every dimension**
No code chunks were extracted — the candidate's repos may contain only non-Python/JS files, or all files were filtered out by the pruner.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18, Vite, Tailwind CSS, Recharts, Lucide Icons |
| Backend | FastAPI, Uvicorn, Python 3.10+ |
| Code Parsing | Tree-sitter (Python + JavaScript grammars) |
| Vector Store | In-memory cosine similarity (Ollama embeddings / TF-IDF fallback) |
| LLM | Ollama — llama3.2 (local, no API key required) |
| Embeddings | Ollama — nomic-embed-text |
| GitHub Data | GitHub REST API v3 |
| PDF Export | jsPDF + html2canvas |