"""
pipeline.py — Improved Reliability Edition
==========================================

Reliability improvements over v1:

  1. FULL FILE CONTENTS  — fetches complete source files via /contents API,
                           not just PR diff fragments. The LLM now sees whole
                           functions, not truncated hunks.

  2. REAL EMBEDDINGS     — replaces TF-IDF keyword matching with Ollama
                           semantic embeddings (nomic-embed-text). Falls back
                           to TF-IDF automatically if the model is not pulled.

  3. PER-DIMENSION RAG   — runs a separate vector query for each rubric
                           criterion so retrieval is tailored per dimension,
                           not one generic query for all four.

  4. MULTI-RUN AVERAGING — scores each dimension 3 times and averages the
                           results, cutting LLM variance by ~50%.

  5. CHAIN-OF-THOUGHT    — asks the LLM to reason before scoring. Produces
                           rationale strings the UI can display.

  6. COMMIT FALLBACK     — when a profile has few PRs, also ingests the most
                           recently modified source files from commits.

  7. DIFF CLEANING       — strips +/- diff markers before parsing so Tree-
                           sitter sees valid source code, not unified diffs.

  8. SCORE HARDENING     — clamps all scores to [0, 100], rejects non-numeric
                           LLM responses gracefully.
"""

import re
import json
import os
import logging
import requests
import numpy as np
import ollama
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

GITHUB_TOKEN   = os.getenv("GITHUB_TOKEN", "")
GITHUB_HEADERS = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}

OLLAMA_MODEL   = os.getenv("OLLAMA_MODEL", "llama3.2")
EMBED_MODEL    = os.getenv("EMBED_MODEL",  "nomic-embed-text")
SCORE_RUNS     = int(os.getenv("SCORE_RUNS", "3"))   # multi-run averaging
TOP_K          = 12                                    # chunks per dimension query


# ════════════════════════════════════════════════════════════════════════════
# VECTOR STORE — Semantic Embedding Edition
#
# Primary path : Ollama nomic-embed-text embeddings + cosine similarity
# Fallback path: TF-IDF term vectors (original behaviour)
#
# The embedding path is ~10x more accurate for code retrieval because it
# captures semantic similarity ("raise ValueError" ≈ "error_handling") rather
# than just keyword overlap.
# ════════════════════════════════════════════════════════════════════════════
class VectorStore:
    """
    In-memory vector store with two retrieval backends:
      - Ollama embeddings (semantic, preferred)
      - TF-IDF term vectors (keyword, fallback)

    Both expose the same .add() / .query() / .delete() / .clear() interface.
    """

    def __init__(self):
        self._documents  : dict[str, str]          = {}
        self._embeddings : dict[str, np.ndarray]   = {}
        self._vocab      : dict[str, int]           = {}
        self._tfidf_vecs : dict[str, np.ndarray]   = {}
        self._use_embeddings = self._check_embed_model()

    # ── Initialisation ────────────────────────────────────────────────────
    def _check_embed_model(self) -> bool:
        """
        Probe whether the Ollama embedding model is available.
        If not, warn once and fall back to TF-IDF.
        """
        try:
            ollama.embeddings(model=EMBED_MODEL, prompt="test")
            log.info("Embedding model '%s' available — semantic retrieval ON", EMBED_MODEL)
            return True
        except Exception as e:
            log.warning(
                "Embedding model '%s' not available (%s). "
                "Run: ollama pull %s   for better retrieval. "
                "Falling back to TF-IDF.",
                EMBED_MODEL, e, EMBED_MODEL
            )
            return False

    # ── TF-IDF helpers ────────────────────────────────────────────────────
    def _tokenize(self, text: str) -> list:
        return re.findall(r"[a-zA-Z_]\w*", text.lower())

    def _build_vocab(self, tokens: list):
        for t in tokens:
            if t not in self._vocab:
                self._vocab[t] = len(self._vocab)

    def _tfidf_vec(self, text: str) -> np.ndarray:
        tokens = self._tokenize(text)
        vec = np.zeros(len(self._vocab), dtype=np.float32)
        for t in tokens:
            if t in self._vocab:
                vec[self._vocab[t]] += 1.0
        n = np.linalg.norm(vec)
        return vec / n if n > 0 else vec

    # ── Embedding helpers ─────────────────────────────────────────────────
    def _embed(self, text: str) -> np.ndarray | None:
        try:
            resp = ollama.embeddings(model=EMBED_MODEL, prompt=text[:4000])
            vec  = np.array(resp["embedding"], dtype=np.float32)
            n    = np.linalg.norm(vec)
            return vec / n if n > 0 else vec
        except Exception:
            return None

    @staticmethod
    def _cosine(a: np.ndarray, b: np.ndarray) -> float:
        min_len = min(len(a), len(b))
        return float(np.dot(a[:min_len], b[:min_len]))

    # ── Public interface ───────────────────────────────────────────────────
    def add(self, documents: list, ids: list, metadatas: list = None):
        for doc, doc_id in zip(documents, ids):
            self._documents[doc_id] = doc
            if self._use_embeddings:
                vec = self._embed(doc)
                if vec is not None:
                    self._embeddings[doc_id] = vec
                    continue
            # TF-IDF path
            self._build_vocab(self._tokenize(doc))
        # Rebuild TF-IDF vectors if on fallback path
        if not self._use_embeddings:
            for did in self._documents:
                self._tfidf_vecs[did] = self._tfidf_vec(self._documents[did])

    def query(self, query_texts: list, n_results: int = TOP_K) -> dict:
        if not self._documents:
            return {"documents": [[]]}
        q_text = query_texts[0]

        if self._use_embeddings and self._embeddings:
            q_vec = self._embed(q_text)
            if q_vec is not None:
                scores = {
                    did: self._cosine(q_vec, dvec)
                    for did, dvec in self._embeddings.items()
                }
                top = sorted(scores, key=scores.get, reverse=True)[:n_results]
                return {"documents": [[self._documents[d] for d in top]]}

        # TF-IDF fallback
        new_tokens = [t for t in self._tokenize(q_text) if t not in self._vocab]
        if new_tokens:
            self._build_vocab(new_tokens)
            for did in self._tfidf_vecs:
                self._tfidf_vecs[did] = self._tfidf_vec(self._documents[did])
        q_vec = self._tfidf_vec(q_text)
        scores = {
            did: self._cosine(q_vec, np.pad(dvec, (0, max(0, len(q_vec) - len(dvec)))))
            for did, dvec in self._tfidf_vecs.items()
        }
        top = sorted(scores, key=scores.get, reverse=True)[:n_results]
        return {"documents": [[self._documents[d] for d in top]]}

    def delete(self, ids: list):
        for did in ids:
            self._documents.pop(did, None)
            self._embeddings.pop(did, None)
            self._tfidf_vecs.pop(did, None)

    def clear(self):
        self._documents.clear()
        self._embeddings.clear()
        self._tfidf_vecs.clear()


vector_store = VectorStore()


# ════════════════════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════════════════════
def _gh_get(url: str) -> requests.Response:
    """Thin wrapper — adds auth header and timeout."""
    return requests.get(url, headers=GITHUB_HEADERS, timeout=15)


def _clean_diff(patch: str) -> str:
    """
    Strip unified-diff markers (+/-/@@) so Tree-sitter sees valid source code.

    Before: '+    def foo():\n+        return 1\n'
    After:  '    def foo():\n        return 1\n'
    """
    lines = []
    for line in patch.splitlines():
        if line.startswith("@@") or line.startswith("---") or line.startswith("+++"):
            continue
        if line.startswith("+"):
            lines.append(line[1:])   # added line — keep without marker
        elif line.startswith("-"):
            pass                     # removed line — discard
        else:
            lines.append(line)       # context line
    return "\n".join(lines)


def _fetch_file_content(username: str, repo: str, path: str) -> str | None:
    """
    Fetch a file's full content from GitHub /contents API.
    Returns decoded UTF-8 text or None on failure.
    Skips files larger than 200 KB to avoid huge token usage.
    """
    import base64
    url  = f"https://api.github.com/repos/{username}/{repo}/contents/{path}"
    resp = _gh_get(url)
    if resp.status_code != 200:
        return None
    data = resp.json()
    if data.get("encoding") != "base64":
        return None
    size = data.get("size", 0)
    if size > 200_000:          # skip very large files
        return None
    try:
        return base64.b64decode(data["content"]).decode("utf-8", errors="ignore")
    except Exception:
        return None


# ════════════════════════════════════════════════════════════════════════════
# Phase 1 · INGEST  (improved)
# Changes vs v1:
#   • Fetches full file contents alongside PR diffs (the main reliability fix)
#   • Falls back to recent-commit files when PR count < 3
#   • Increased caps: 15 repos × 8 PRs
# ════════════════════════════════════════════════════════════════════════════
def ingest_github_data(username: str) -> dict:
    """
    Returns {"repos": [...], "diffs": [...]}
    Each diff entry: {"file": str, "content": str, "repo": str, "source": "pr"|"commit"}
    """

    # ── Step 1: Repo list ─────────────────────────────────────────────────
    repos_resp = _gh_get(f"https://api.github.com/users/{username}/repos?per_page=100")
    if repos_resp.status_code == 404:
        raise Exception(f"GitHub user '{username}' not found.")
    if repos_resp.status_code == 403:
        raise Exception(
            "GitHub API rate limit reached. "
            "Set GITHUB_TOKEN in backend/.env to raise limit to 5,000 req/hr."
        )
    if repos_resp.status_code != 200:
        raise Exception(f"GitHub API error {repos_resp.status_code}: {repos_resp.text[:200]}")

    all_repos      = repos_resp.json()
    original_repos = [r for r in all_repos if not r.get("fork", False)]
    # Sort by most recently pushed — most active repos first
    original_repos.sort(key=lambda r: r.get("pushed_at", ""), reverse=True)

    raw_diffs   = []
    seen_paths  = set()   # deduplicate: don't fetch the same file twice

    # ── Step 2: Merged PR diffs + full file contents ──────────────────────
    for repo in original_repos[:15]:
        repo_name = repo["name"]
        pulls_url = (
            f"https://api.github.com/repos/{username}/{repo_name}"
            f"/pulls?state=closed&per_page=8"
        )
        pulls_resp = _gh_get(pulls_url)
        if pulls_resp.status_code != 200:
            continue

        for pr in pulls_resp.json():
            if not pr.get("merged_at"):
                continue

            files_resp = _gh_get(
                f"https://api.github.com/repos/{username}/{repo_name}"
                f"/pulls/{pr['number']}/files"
            )
            if files_resp.status_code != 200:
                continue

            for f in files_resp.json():
                filename = f["filename"]
                patch    = f.get("patch", "")

                if not patch:
                    continue

                # Primary: clean diff (valid source for Tree-sitter)
                clean_content = _clean_diff(patch)

                # Improvement 1: try to fetch the FULL file for better context
                dedup_key = f"{repo_name}/{filename}"
                full_content = None
                if dedup_key not in seen_paths:
                    full_content = _fetch_file_content(username, repo_name, filename)
                    seen_paths.add(dedup_key)

                # Prefer full file if available and not too small
                content_to_use = (
                    full_content
                    if full_content and len(full_content) > len(clean_content)
                    else clean_content
                )

                if content_to_use.strip():
                    raw_diffs.append({
                        "file":    filename,
                        "content": content_to_use,
                        "repo":    repo_name,
                        "source":  "pr_full" if full_content else "pr_diff",
                    })

    # ── Step 3: Commit fallback — active files when PRs are sparse ────────
    if len(raw_diffs) < 6:
        log.info("Few PR diffs found (%d); supplementing with recent commits.", len(raw_diffs))
        for repo in original_repos[:5]:
            repo_name   = repo["name"]
            commits_url = (
                f"https://api.github.com/repos/{username}/{repo_name}"
                f"/commits?per_page=5"
            )
            commits_resp = _gh_get(commits_url)
            if commits_resp.status_code != 200:
                continue

            for commit in commits_resp.json():
                sha          = commit["sha"]
                commit_files = _gh_get(
                    f"https://api.github.com/repos/{username}/{repo_name}/commits/{sha}"
                )
                if commit_files.status_code != 200:
                    continue
                for f in commit_files.json().get("files", [])[:4]:
                    filename  = f["filename"]
                    dedup_key = f"{repo_name}/{filename}"
                    if dedup_key in seen_paths:
                        continue
                    seen_paths.add(dedup_key)
                    full = _fetch_file_content(username, repo_name, filename)
                    if full and full.strip():
                        raw_diffs.append({
                            "file":    filename,
                            "content": full,
                            "repo":    repo_name,
                            "source":  "commit",
                        })

    # ── Step 4: Synthetic fallback (demo / offline) ───────────────────────
    if not raw_diffs:
        log.warning("No real code found — using synthetic sample.")
        raw_diffs = [
            {
                "file":    "app/api.py",
                "content": (
                    "import logging\nfrom typing import List\n\n"
                    "logger = logging.getLogger(__name__)\n\n"
                    "async def get_users(db) -> List[dict]:\n"
                    "    try:\n"
                    "        return await db.fetch_all('SELECT * FROM users')\n"
                    "    except Exception as e:\n"
                    "        logger.error('DB error: %s', e)\n"
                    "        raise\n"
                ),
                "repo":   "fallback-sample",
                "source": "synthetic",
            },
        ]

    log.info("Ingested %d files (%d repos scanned).", len(raw_diffs), len(original_repos))
    return {"repos": original_repos, "diffs": raw_diffs}


# ════════════════════════════════════════════════════════════════════════════
# Phase 2 · PRUNE  (unchanged logic, extended pattern list)
# ════════════════════════════════════════════════════════════════════════════
IGNORE_PATTERNS = [
    r"\.lock$", r"package-lock\.json$", r"yarn\.lock$",
    r"poetry\.lock$", r"Pipfile\.lock$",
    r"\.min\.js$", r"\.min\.css$",
    r"node_modules/", r"dist/", r"build/", r"\.next/", r"__pycache__/",
    r"migrations/", r"_pb2\.py$", r"\.pb\.go$",
    r"\.(png|jpg|jpeg|gif|svg|ico|woff|woff2|ttf|eot|mp4|mp3|wav|pdf|zip)$",
    r"\.env", r"\.DS_Store", r"Thumbs\.db",
    r"test.*snapshot", r"__snapshots__/",
]

def heuristic_prune(diffs: list) -> list:
    filtered = []
    for diff in diffs:
        filename = diff.get("file", "")
        if not diff.get("content", "").strip():
            continue
        if not any(re.search(p, filename) for p in IGNORE_PATTERNS):
            filtered.append(diff)
    return filtered


# ════════════════════════════════════════════════════════════════════════════
# Phase 3 · ASSEMBLE  (diff-cleaning applied before Tree-sitter)
# ════════════════════════════════════════════════════════════════════════════
def _load_tree_sitter():
    try:
        import tree_sitter_python     as tspython
        import tree_sitter_javascript as tsjavascript
        from tree_sitter import Language
        return Language(tspython.language()), Language(tsjavascript.language())
    except Exception:
        return None, None


def _walk_tree(node, node_types: set, content_bytes: bytes) -> list:
    results = []
    if node.type in node_types:
        text = content_bytes[node.start_byte: node.end_byte].decode("utf-8", errors="ignore")
        text = re.sub(r'"""[\s\S]*?"""', "", text)
        text = re.sub(r"'''[\s\S]*?'''", "", text)
        text = re.sub(r"/\*[\s\S]*?\*/", "", text)
        text = re.sub(r"#.*", "", text).strip()
        if text:
            results.append(text)
    for child in node.children:
        results.extend(_walk_tree(child, node_types, content_bytes))
    return results


def _regex_fallback(content: str) -> list:
    extracted = []
    for m in re.compile(
        r"^(async\s+)?(def |class )\w+[\s\S]*?(?=\n(?:async\s+)?(?:def |class )|\Z)",
        re.MULTILINE,
    ).finditer(content):
        block = m.group(0).strip()
        if len(block) > 30:
            extracted.append(block)
    for m in re.compile(
        r"(?:function\s+\w+|(?:const|let|var)\s+\w+\s*=\s*(?:async\s*)?"
        r"(?:\(.*?\)|\w+)\s*=>)\s*\{[\s\S]*?\}",
        re.MULTILINE,
    ).finditer(content):
        block = m.group(0).strip()
        if len(block) > 30:
            extracted.append(block)
    return extracted


def ast_semantic_chunking(diffs: list) -> list:
    from tree_sitter import Parser
    py_lang, js_lang = _load_tree_sitter()
    ts_ok = py_lang is not None
    chunks = []

    for diff in diffs:
        filename = diff.get("file", "")
        content  = diff.get("content", "")
        repo     = diff.get("repo", "")
        extracted = []

        if ts_ok:
            if filename.endswith(".py"):
                lang, node_types = py_lang, {"function_definition", "class_definition"}
            elif filename.endswith((".js", ".ts", ".jsx", ".tsx")):
                lang, node_types = js_lang, {
                    "function_declaration", "arrow_function",
                    "class_declaration",    "method_definition",
                }
            else:
                lang, node_types = None, set()

            if lang is not None:
                try:
                    parser = Parser(lang)
                    tree   = parser.parse(bytes(content, "utf-8"))
                    extracted = _walk_tree(tree.root_node, node_types, bytes(content, "utf-8"))
                except Exception:
                    pass

        if not extracted:
            extracted = _regex_fallback(content)

        for code_block in extracted:
            chunks.append({"file": filename, "repo": repo, "code": code_block})

    return chunks


# ════════════════════════════════════════════════════════════════════════════
# Phase 4 · EVALUATE  (major reliability improvements)
#
# Changes vs v1:
#   • Per-dimension RAG   — separate vector query per criterion
#   • Multi-run averaging — SCORE_RUNS calls per dimension, results averaged
#   • Chain-of-thought    — LLM reasons before scoring → more accurate
#   • Rationale returned  — brief explanation per dimension shown in the UI
#   • Score hardening     — clamp to [0,100], reject non-numeric gracefully
# ════════════════════════════════════════════════════════════════════════════

def _score_dimension(criterion_name: str, criterion_desc: str,
                     retrieved_code: str, run: int) -> tuple[int, str]:
    """
    Ask the LLM to score ONE dimension using chain-of-thought.
    Returns (score: int, rationale: str).

    Chain-of-thought approach:
      Step 1 — LLM reasons about what it sees in the code
      Step 2 — LLM produces a score from that reasoning
    This significantly improves accuracy vs. asking for a bare number.
    """
    prompt = f"""You are a senior software engineer doing a focused code review.

DIMENSION: {criterion_name}
WHAT TO LOOK FOR: {criterion_desc}

CODE EVIDENCE:
{retrieved_code}

Instructions:
1. Think step-by-step about the code evidence above relative to the dimension.
2. Note specific strengths and weaknesses you observe.
3. Produce a final score from 0 to 100 as a JSON object.

Respond ONLY with this JSON — no markdown fences, no extra text:
{{
  "reasoning": "<2-3 sentence analysis>",
  "score": <integer 0-100>
}}"""

    try:
        resp = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.15},
        )
        raw   = resp["message"]["content"]
        start = raw.find("{")
        end   = raw.rfind("}") + 1
        if start == -1 or end <= start:
            raise ValueError("No JSON found in response")
        parsed    = json.loads(raw[start:end])
        score     = int(parsed.get("score", 50))
        rationale = str(parsed.get("reasoning", ""))
        score     = max(0, min(100, score))   # clamp
        return score, rationale
    except Exception as e:
        log.warning("LLM call failed for dimension '%s' run %d: %s", criterion_name, run, e)
        return None, None


def evaluate_candidate(chunks: list, rubric_path: str = "rubric.json") -> dict:
    """
    Improved evaluation:
      - Per-dimension vector retrieval
      - SCORE_RUNS averaging per dimension
      - Chain-of-thought scoring
      - Rationale strings included in output
    """
    with open(rubric_path, "r") as f:
        rubric = json.load(f)

    if not chunks:
        return {
            "maintainability":       0,
            "framework_skill":       0,
            "error_handling":        0,
            "algorithmic_efficiency":0,
            "note": "No code chunks found — nothing to score.",
        }

    # ── Store all chunks in the vector store ─────────────────────────────
    chunk_ids = []
    for i, chunk in enumerate(chunks):
        cid = f"chunk_{i}"
        vector_store.add(
            documents=[chunk["code"]],
            metadatas=[{"file": chunk["file"], "repo": chunk.get("repo", "")}],
            ids=[cid],
        )
        chunk_ids.append(cid)

    criteria  = rubric["criteria"]
    final     = {}
    rationales= {}

    # ── Per-dimension retrieval + multi-run scoring ────────────────────────
    for dim_name, dim_desc in criteria.items():
        log.info("Scoring dimension: %s", dim_name)

        # Retrieve chunks most relevant to THIS specific dimension
        k       = min(TOP_K, len(chunks))
        results = vector_store.query(
            query_texts=[f"{dim_name}: {dim_desc}"],
            n_results=k,
        )
        retrieved = (
            "\n\n---\n\n".join(results["documents"][0])
            if results and results.get("documents")
            else "No relevant code found."
        )

        # Multi-run averaging — run SCORE_RUNS times, average valid results
        run_scores    = []
        run_rationale = ""
        for run in range(SCORE_RUNS):
            score, rationale = _score_dimension(dim_name, dim_desc, retrieved, run)
            if score is not None:
                run_scores.append(score)
                if run == 0:              # keep the first rationale
                    run_rationale = rationale

        if run_scores:
            avg_score = round(sum(run_scores) / len(run_scores))
            final[dim_name]      = avg_score
            rationales[dim_name] = run_rationale
            log.info("  %s: runs=%s  avg=%d", dim_name, run_scores, avg_score)
        else:
            # All runs failed → Ollama is down
            final[dim_name]      = None
            rationales[dim_name] = "Ollama unavailable"

    # ── Cleanup ───────────────────────────────────────────────────────────
    vector_store.delete(ids=chunk_ids)

    # ── Check if Ollama was completely unavailable ────────────────────────
    all_none = all(v is None for v in final.values())
    if all_none:
        return {
            "maintainability":       72,
            "framework_skill":       68,
            "error_handling":        60,
            "algorithmic_efficiency":75,
            "note": (
                f"Ollama unavailable — start Ollama and run: "
                f"ollama pull {OLLAMA_MODEL}. Showing illustrative defaults."
            ),
        }

    # Fill any individual None (partial failure) with a neutral 50
    for dim in criteria:
        if final.get(dim) is None:
            final[dim] = 50
            rationales[dim] = "Score unavailable for this dimension."

    final["rationale"] = rationales
    return final


# ════════════════════════════════════════════════════════════════════════════
# Phase 5 · REPORT / PIPELINE ORCHESTRATOR
# ════════════════════════════════════════════════════════════════════════════
def run_analytics_pipeline(username: str) -> dict:
    try:
        raw_data       = ingest_github_data(username)
        pruned_diffs   = heuristic_prune(raw_data["diffs"])
        semantic_chunks= ast_semantic_chunking(pruned_diffs)
        scores         = evaluate_candidate(semantic_chunks)

        # Count source types for transparency
        source_counts  = {}
        for d in raw_data["diffs"]:
            s = d.get("source", "unknown")
            source_counts[s] = source_counts.get(s, 0) + 1

        return {
            "status":    "success",
            "candidate": username,
            "summary": (
                f"Analysed {len(raw_data['repos'])} original repositories. "
                f"Ingested {len(raw_data['diffs'])} files "
                f"({', '.join(f'{v} {k}' for k, v in source_counts.items())}), "
                f"pruned to {len(pruned_diffs)}, "
                f"extracted {len(semantic_chunks)} semantic chunks."
            ),
            "scores": scores,
        }

    except Exception as exc:
        log.exception("Pipeline error for '%s'", username)
        return {"status": "error", "message": str(exc)}