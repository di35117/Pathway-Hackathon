"""
LiveCold RAG Pipeline - Pure Pathway Framework
Complete RAG implementation using Pathway DocumentStore with Gemini + SentenceTransformers

Uses BaseRAGQuestionAnswerer for proper streaming RAG with built-in REST API.

Endpoints (after running):
  POST /v2/answer     - Query with LLM-generated answer + SOP citations
  POST /v2/retrieve   - Retrieve documents only
  POST /v2/inputs     - List indexed documents
  POST /v2/statistics - Index statistics
"""

import pathway as pw
from pathway.xpacks.llm import embedders, parsers, splitters, llms
from pathway.xpacks.llm.document_store import DocumentStore
from pathway.xpacks.llm.question_answering import BaseRAGQuestionAnswerer
from pathway.stdlib.indexing.nearest_neighbors import BruteForceKnnFactory, BruteForceKnnMetricKind
import os
from dotenv import load_dotenv

# Load .env file (API keys)
load_dotenv()

# Configuration
WATCHED_DOCS_DIR = "./watched_docs"
GEMINI_MODEL = "gemini/gemini-2.5-flash"  # LiteLLM format
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
CHUNK_SIZE = 500
MIN_CHUNK_SIZE = 100

# Custom prompt template enforcing SOP citations
LIVECOLD_PROMPT_TEMPLATE = """You are a cold-chain compliance assistant for LiveCold.
Use ONLY the context below to answer the question.
If the answer cannot be found in the context, say "I could not find relevant SOP guidance."

Context:
{context}

Question: {query}

Instructions:
1. Provide a numbered action checklist
2. Cite specific SOP sections using format: "Per SOP §X.Y, [action]"
3. Include any relevant temperature thresholds or time limits from the SOPs
4. End with: "⚠️ Final decision requires human approval."

Answer:"""


class LiveColdRAGPipeline:
    """Complete Pathway-based RAG pipeline using BaseRAGQuestionAnswerer"""

    def __init__(self):
        # Verify API keys — checks GEMINI_API_KEY first, falls back to GOOGLE_API_KEY
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("API key not set. Add GEMINI_API_KEY or GOOGLE_API_KEY to your .env file")
        # Ensure GEMINI_API_KEY is set for LiteLLM
        os.environ["GEMINI_API_KEY"] = api_key

        os.makedirs(WATCHED_DOCS_DIR, exist_ok=True)

    def build_document_store(self):
        """Build Pathway DocumentStore with real-time document monitoring"""

        print("Building Pathway DocumentStore...")

        # STEP 1: Document Input Stream (Real-time monitoring)
        # Pathway automatically monitors this directory for changes
        documents = pw.io.fs.read(
            path=WATCHED_DOCS_DIR,
            format="binary",
            mode="streaming",  # Real-time updates!
            with_metadata=True
        )

        print(f"  ✓ Watching documents in: {WATCHED_DOCS_DIR}")

        # STEP 2: Parser - Extract text from documents
        parser = parsers.UnstructuredParser()

        # STEP 3: Splitter - Break into chunks
        text_splitter = splitters.TokenCountSplitter(
            min_tokens=MIN_CHUNK_SIZE,
            max_tokens=CHUNK_SIZE,
            encoding_name="cl100k_base"
        )

        # STEP 4: Embedder - Use SentenceTransformers (local, free!)
        embedder = embedders.SentenceTransformerEmbedder(
            model=EMBEDDING_MODEL
        )

        print(f"  ✓ Embedder: {EMBEDDING_MODEL}")

        # STEP 5: Retriever - Brute force KNN
        retriever_factory = BruteForceKnnFactory(
            embedder=embedder,
            dimensions=384,  # all-MiniLM-L6-v2 dimension
            reserved_space=1000,
            metric=BruteForceKnnMetricKind.COS
        )

        # STEP 6: Create DocumentStore (handles parsing, splitting, embedding, retrieval)
        doc_store = DocumentStore(
            docs=documents,
            retriever_factory=retriever_factory,
            parser=parser,
            splitter=text_splitter
        )

        print("  ✓ DocumentStore created")

        return doc_store

    def build_llm(self):
        """Create Gemini LLM via LiteLLM wrapper"""

        chat = llms.LiteLLMChat(
            model=GEMINI_MODEL,
            api_key=os.getenv("GEMINI_API_KEY"),
            temperature=0.0,
            capacity=10,
            retry_strategy=pw.udfs.ExponentialBackoffRetryStrategy(
                max_retries=3,
                initial_delay=1000
            )
        )

        print(f"  ✓ LLM: {GEMINI_MODEL}")

        return chat

    def run(self, host="0.0.0.0", port=8765):
        """Build and run the complete RAG pipeline with REST API"""

        print("\n" + "=" * 60)
        print("LiveCold RAG Pipeline")
        print("=" * 60)

        # 1. Build DocumentStore (indexer)
        doc_store = self.build_document_store()

        # 2. Build LLM
        chat = self.build_llm()

        # 3. Create RAG application using Pathway's BaseRAGQuestionAnswerer
        # This handles retrieval + LLM answering + REST API natively
        rag_app = BaseRAGQuestionAnswerer(
            llm=chat,
            indexer=doc_store,
            prompt_template=LIVECOLD_PROMPT_TEMPLATE,
            search_topk=6
        )

        print("  ✓ RAG application created")

        # 4. Build REST server (adds HTTP connectors)
        rag_app.build_server(host=host, port=port)

        print(f"\n{'=' * 60}")
        print("🚀 LiveCold RAG Pipeline Running")
        print("=" * 60)
        print(f"📁 Watching: {WATCHED_DOCS_DIR}")
        print(f"🤖 LLM: {GEMINI_MODEL}")
        print(f"📊 Embedder: {EMBEDDING_MODEL}")
        print(f"🌐 API: http://{host}:{port}")
        print()
        print("Endpoints:")
        print(f"  POST http://localhost:{port}/v2/answer     - Query with LLM answer")
        print(f"  POST http://localhost:{port}/v2/retrieve   - Retrieve docs only")
        print(f"  POST http://localhost:{port}/v2/inputs     - List indexed documents")
        print(f"  POST http://localhost:{port}/v2/statistics  - Index statistics")
        print()
        print("Example query:")
        print(f'  curl -X POST http://localhost:{port}/v2/answer \\')
        print(f'    -H "Content-Type: application/json" \\')
        print(f'    -d \'{{"prompt": "What should I do if temperature exceeds threshold?"}}\'')
        print("=" * 60 + "\n")

        # 5. Run Pathway — this starts the streaming pipeline + REST server
        # Blocks until interrupted (Ctrl+C)
        pw.run()


# Alternative: Create a pipeline for integration with the full pipeline
def create_rag_for_integration():
    """
    Create RAG components (doc_store + llm) for use in the integrated pipeline.
    Use this when you want to embed RAG into the main pipeline.

    Returns:
        tuple: (doc_store, chat_llm) for use in pathway_integrated_full.py
    """

    pipeline = LiveColdRAGPipeline()
    doc_store = pipeline.build_document_store()
    chat = pipeline.build_llm()

    return doc_store, chat


if __name__ == "__main__":
    # Run the standalone RAG pipeline
    pipeline = LiveColdRAGPipeline()
    pipeline.run(
        host="0.0.0.0",
        port=8765
    )
