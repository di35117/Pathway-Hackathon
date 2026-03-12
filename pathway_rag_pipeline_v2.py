"""
LiveCold RAG Pipeline V2 - Pathway Framework (REAL-TIME)
Real-time SOP document monitoring & LLM-powered Q&A using Pathway.

KEY DIFFERENCE from V1:
  - V1 loaded SOP text once at startup into a static variable (stale).
  - V2 uses Pathway's pw.io.fs.read(mode="streaming") to detect file changes.
    When the SOP file is modified, Pathway's dataflow re-processes documents,
    which triggers re-evaluation of queries. The build_answer UDF always reads
    the latest file content, giving real-time answers.

Endpoints (after running):
  POST /v2/answer  {"prompt": "your question"}  → LLM answer with live SOP
"""

import pathway as pw
import os
import json
import time
import hashlib
import threading
from datetime import datetime
from dotenv import load_dotenv
import litellm as _litellm

load_dotenv()

# Configuration
WATCHED_DOCS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "watched_docs")
GEMINI_MODEL = "gemini/gemini-2.5-flash"

# Thread-safe SOP sync tracking (shared with dashboard if imported)
_sop_lock = threading.Lock()
_sop_last_sync = {"timestamp": None, "char_count": 0, "doc_count": 0}

# Custom prompt template
PROMPT_TEMPLATE = """You are a cold-chain compliance assistant for LiveCold.
Use ONLY the context below to answer the question.
If the answer cannot be found in the context, say "I could not find relevant SOP guidance."

Context:
{context}

Question: {query}

Instructions:
1. Provide a numbered action checklist (max 4 items)
2. Cite specific SOP sections using format: "Per SOP §X.Y, [action]"
3. Include any relevant temperature thresholds or time limits
4. End with: "⚠️ Final decision requires human approval."

Answer:"""


def _update_sync_status(char_count: int, doc_count: int):
    """Thread-safe update of SOP sync timestamp."""
    with _sop_lock:
        _sop_last_sync["timestamp"] = datetime.now().isoformat()
        _sop_last_sync["char_count"] = char_count
        _sop_last_sync["doc_count"] = doc_count


def get_sop_sync_status() -> dict:
    """Get the last SOP sync status (used by dashboard)."""
    with _sop_lock:
        return dict(_sop_last_sync)


# ── SOP file cache with hash-based invalidation ────────────────
_sop_cache = {"content": None, "hash": None}


def _read_sop_files_from_disk() -> str:
    """Read all SOP files directly from disk (always fresh)."""
    context_parts = []
    try:
        for fname in sorted(os.listdir(WATCHED_DOCS_DIR)):
            fpath = os.path.join(WATCHED_DOCS_DIR, fname)
            if os.path.isfile(fpath) and not fname.startswith('.'):
                with open(fpath, "r", errors="replace") as f:
                    content = f.read()
                    if content.strip():
                        context_parts.append(content)
    except Exception as e:
        print(f"  ⚠ Error reading SOP files: {e}")
    
    joined = "\n\n".join(context_parts)
    _update_sync_status(len(joined), len(context_parts))
    return joined


def _read_sop_files_cached() -> str:
    """Read SOP files with content-hash cache — only re-reads if files changed."""
    file_hashes = []
    try:
        for fname in sorted(os.listdir(WATCHED_DOCS_DIR)):
            fpath = os.path.join(WATCHED_DOCS_DIR, fname)
            if os.path.isfile(fpath) and not fname.startswith('.'):
                stat = os.stat(fpath)
                file_hashes.append(f"{fname}:{stat.st_mtime}:{stat.st_size}")
    except Exception as e:
        print(f"  ⚠ Error checking SOP files: {e}")
        return _sop_cache["content"] or ""

    current_hash = hashlib.md5("|".join(file_hashes).encode()).hexdigest()

    if _sop_cache["hash"] == current_hash and _sop_cache["content"]:
        return _sop_cache["content"]  # Cache hit — no disk I/O

    # Cache miss — read from disk
    context = _read_sop_files_from_disk()
    _sop_cache["content"] = context
    _sop_cache["hash"] = current_hash
    return context


def _get_relevant_chunks(query: str, sop_text: str, max_chars: int = 4000) -> str:
    """Simple keyword-based relevance filtering to reduce prompt size."""
    chunks = sop_text.split("\n\n")
    query_words = set(query.lower().split())

    scored = []
    for chunk in chunks:
        if not chunk.strip():
            continue
        chunk_words = set(chunk.lower().split())
        overlap = len(query_words & chunk_words)
        scored.append((overlap, chunk))

    scored.sort(key=lambda x: x[0], reverse=True)

    result = []
    total = 0
    for _, chunk in scored:
        if total + len(chunk) > max_chars:
            break
        result.append(chunk)
        total += len(chunk)

    return "\n\n".join(result) if result else sop_text[:max_chars]


# ── Pathway UDFs ────────────────────────────────────────────────

@pw.udf
def decode_document(data: bytes) -> str:
    """Decode binary document content from pw.io.fs.read to text."""
    try:
        text = data.decode("utf-8", errors="replace")
        # Update sync timestamp whenever Pathway processes a document change
        _update_sync_status(len(text), 1)
        print(f"  🔄 SOP document processed by Pathway: {len(text)} chars at {datetime.now().strftime('%H:%M:%S')}")
        return text
    except Exception:
        return ""


# Track last-working key/model combo to skip known-bad ones
_last_working = {"api_key": None, "model": None}


@pw.udf
def build_answer(query: str) -> str:
    """Call LLM with LIVE SOP context to answer the query.
    
    Optimizations over V1:
    - Uses cached SOP reads (only re-reads on file change)
    - Relevance-filters context to reduce prompt token count
    - Tries last-working key/model first to avoid fallback cascade
    - Reduced timeout (10s vs 30s)
    """
    global _last_working

    # Read SOP content with cache (only re-reads if files changed)
    sop_context = _read_sop_files_cached()
    
    if not sop_context:
        return "No SOP documents found in watched_docs directory."

    # Build API key list
    api_keys = []
    for var in ["GOOGLE_API_KEY_imp", "GOOGLE_API_KEY", "GOOGLE_API_KEY_2", "GEMINI_API_KEY"]:
        k = os.getenv(var)
        if k and k not in api_keys:
            api_keys.append(k)

    models = [
        "gemini/gemini-2.5-flash",
        "gemini/gemini-2.0-flash",
        "gemini/gemini-1.5-flash",
    ]

    # Relevance-filter context to reduce prompt size (~4K instead of 12K)
    relevant_context = _get_relevant_chunks(query, sop_context, max_chars=4000)
    prompt = PROMPT_TEMPLATE.format(context=relevant_context, query=query)

    # Try last-working combo first for fast path
    if _last_working["api_key"] and _last_working["model"]:
        try:
            response = _litellm.completion(
                model=_last_working["model"],
                messages=[{"role": "user", "content": prompt}],
                api_key=_last_working["api_key"],
                timeout=10,
                num_retries=0,
            )
            return response.choices[0].message.content.strip()
        except Exception:
            pass  # Fall through to full cascade

    # Full cascade as fallback
    for api_key in api_keys:
        os.environ["GEMINI_API_KEY"] = api_key
        for model in models:
            try:
                response = _litellm.completion(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    api_key=api_key,
                    timeout=10,
                    num_retries=0,
                )
                # Remember this working combo for next time
                _last_working = {"api_key": api_key, "model": model}
                return response.choices[0].message.content.strip()
            except Exception:
                continue

    return "SOP service temporarily unavailable. All models rate-limited."


# ── Pathway Schemas ─────────────────────────────────────────────

class QuerySchema(pw.Schema):
    prompt: str


# ── Main Pipeline ───────────────────────────────────────────────

def run_rag_pipeline(host="0.0.0.0", port=8765):
    """Run the Pathway RAG pipeline V2 with LIVE document updates."""

    print("\n" + "=" * 60)
    print("LiveCold Pathway RAG Pipeline V2 (REAL-TIME)")
    print("=" * 60)

    # ── Step 1: Monitor SOP documents in real-time ──────────────
    # Pathway watches this directory in streaming mode. When a file
    # changes, Pathway reprocesses the dataflow graph.
    documents = pw.io.fs.read(
        path=WATCHED_DOCS_DIR,
        format="binary",
        mode="streaming",
        with_metadata=True,
    )
    print(f"  ✓ pw.io.fs.read watching: {WATCHED_DOCS_DIR}")

    # ── Step 2: Decode documents (triggers on file changes) ─────
    # This step runs whenever Pathway detects a file change.
    # The decode_document UDF updates sync status.
    decoded_docs = documents.select(
        text=decode_document(documents.data),
    )
    print("  ✓ Document decoder UDF attached")

    # ── Step 3: Output decoded docs (keeps the pipeline alive) ──
    # Writing to null output keeps the document-watching part of
    # the dataflow active, so file changes are always detected.
    pw.io.null.write(decoded_docs)
    print("  ✓ Document change monitor active")

    # ── Step 4: REST API input connector ────────────────────────
    queries, response_writer = pw.io.http.rest_connector(
        host=host,
        port=port,
        route="/v2/answer",
        schema=QuerySchema,
        autocommit_duration_ms=500,  # Increased from 50 to reduce framework overhead
        delete_completed_queries=True,
    )
    print(f"  ✓ REST /v2/answer on {host}:{port}")

    # ── Step 5: Process queries through LLM with fresh SOP ──────
    # build_answer reads SOP files directly from disk each time,
    # always getting the latest content.
    results = queries.select(
        result=build_answer(queries.prompt),
    )

    # ── Step 6: Write responses back via REST ──────────────────
    response_writer(results)
    print("  ✓ Response writer connected")

    print(f"\n{'=' * 60}")
    print("🚀 LiveCold Pathway RAG V2 Running (REAL-TIME UPDATES)")
    print("=" * 60)
    print(f"📁 Watching SOPs: {WATCHED_DOCS_DIR}")
    print(f"🤖 LLM: {GEMINI_MODEL}")
    print(f"🌐 Q&A API: http://{host}:{port}/v2/answer")
    print()
    print("🔥 REAL-TIME: Edit any file in watched_docs/ and the next")
    print("   query will automatically use the updated content!")
    print()
    print("Usage:")
    print(f'  curl -X POST http://localhost:{port}/v2/answer \\')
    print(f'    -H "Content-Type: application/json" \\')
    print(f'    -d \'{{"prompt": "What to do if temp exceeds threshold?"}}\'')
    print("=" * 60 + "\n")

    # ── Step 7: Run Pathway — starts streaming pipeline + REST ─
    pw.run()


if __name__ == "__main__":
    run_rag_pipeline()
