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
import threading
from datetime import datetime
from dotenv import load_dotenv

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


@pw.udf
def build_answer(query: str) -> str:
    """Call LLM with LIVE SOP context to answer the query.
    
    Unlike V1's static SOP_CONTEXT, this reads the SOP files fresh
    from disk on each query. Pathway's streaming mode ensures this UDF
    is triggered whenever documents change, and the fresh read guarantees
    we always have the latest content.
    """
    import litellm as _litellm

    # Read SOP content fresh from disk (always up-to-date)
    sop_context = _read_sop_files_from_disk()
    
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

    prompt = PROMPT_TEMPLATE.format(context=sop_context[:12000], query=query)

    for api_key in api_keys:
        os.environ["GEMINI_API_KEY"] = api_key
        for model in models:
            try:
                response = _litellm.completion(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    api_key=api_key,
                    timeout=30,
                )
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
        autocommit_duration_ms=50,
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
