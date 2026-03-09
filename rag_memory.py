"""
rag_memory.py — Vector memory for the bill matcher.

Stores past payment matches (company name → bill) as embeddings so the
bill matcher can retrieve similar historical matches and use them as context.

This is the core enterprise augmentation pattern: layer AI reasoning on top
of data you already have, without modifying the underlying system.

Architecture:
  - Embedding model: sentence-transformers/all-MiniLM-L6-v2 (local, free, ~80MB)
  - Vector store: ChromaDB PersistentClient (local file at ./chroma_db/)
  - Both lazy-loaded on first use to keep startup fast

Multi-user upgrade path:
  - Swap PersistentClient for chromadb.HttpClient(host="localhost", port=8000)
  - Run: chroma run --host localhost --port 8000 --path ./chroma_db
  - That's the only change needed in this file.
"""

import os
import re
from datetime import datetime

# Lazy-loaded globals — initialized on first use
_model = None
_client = None
_collection = None

CHROMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chroma_db")
COLLECTION_NAME = "payment_memory"

# Cosine distance threshold — results above this are too dissimilar to be useful
SIMILARITY_THRESHOLD = 0.5


def _init():
    """Lazy-initialize the embedding model and ChromaDB on first use."""
    global _model, _client, _collection
    if _collection is not None:
        return

    from sentence_transformers import SentenceTransformer
    import chromadb

    _model = SentenceTransformer("all-MiniLM-L6-v2")
    _client = chromadb.PersistentClient(path=CHROMA_PATH)
    _collection = _client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def add_payment_memory(company_name: str, bill_name: str, confidence: str,
                       amount: float = None):
    """
    Store a successful payment match in vector memory.

    Called after HIGH/MEDIUM confidence matches are recorded. LOW confidence
    matches go to the review queue instead and are NOT stored here.

    Args:
        company_name: Company extracted from the email (e.g. "QuickTrip Fuel #421")
        bill_name:    Matched bill name from the database (e.g. "Transportation")
        confidence:   "HIGH" or "MEDIUM" — LOW matches are never stored
        amount:       Payment amount, stored as metadata for reference
    """
    _init()

    embedding = _model.encode(company_name).tolist()

    # Use timestamp suffix to allow multiple entries per company over time
    # (shows consistent pattern, not just one data point)
    doc_id = f"{company_name}__{bill_name}__{datetime.now().strftime('%Y%m%d%H%M%S%f')}"

    _collection.add(
        embeddings=[embedding],
        documents=[company_name],
        metadatas=[{
            "company":     company_name,
            "bill_name":   bill_name,
            "confidence":  confidence,
            "amount":      str(amount) if amount is not None else "",
            "recorded_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }],
        ids=[doc_id],
    )


def get_similar_matches(company_name: str, k: int = 3) -> list:
    """
    Retrieve the k most similar past payment matches for a company name.

    Uses cosine similarity on the embedding of the company name. Only returns
    results with distance < SIMILARITY_THRESHOLD (0.5) — beyond that, the
    match isn't similar enough to be useful context.

    Args:
        company_name: Company name to look up
        k:            Max number of results to return

    Returns:
        List of dicts: [{company, bill_name, confidence, distance}, ...]
        Empty list if no similar matches found or store is empty.
    """
    _init()

    count = _collection.count()
    if count == 0:
        return []

    embedding = _model.encode(company_name).tolist()
    results = _collection.query(
        query_embeddings=[embedding],
        n_results=min(k, count),
        include=["metadatas", "distances", "documents"],
    )

    matches = []
    for i, metadata in enumerate(results["metadatas"][0]):
        distance = results["distances"][0][i]
        if distance < SIMILARITY_THRESHOLD:
            matches.append({
                "company":    metadata["company"],
                "bill_name":  metadata["bill_name"],
                "confidence": metadata["confidence"],
                "distance":   round(distance, 3),
            })

    return matches


def get_all_memories() -> list:
    """
    Return all stored payment memories, sorted newest first.
    Used by the Streamlit UI to display what's in the RAG store.
    """
    _init()

    count = _collection.count()
    if count == 0:
        return []

    results = _collection.get(include=["metadatas", "documents"])

    memories = []
    for metadata in results["metadatas"]:
        memories.append({
            "company":     metadata.get("company", ""),
            "bill_name":   metadata.get("bill_name", ""),
            "confidence":  metadata.get("confidence", ""),
            "amount":      metadata.get("amount", ""),
            "recorded_at": metadata.get("recorded_at", ""),
        })

    return sorted(memories, key=lambda x: x["recorded_at"], reverse=True)


def get_memory_count() -> int:
    """Return total number of stored memories."""
    _init()
    return _collection.count()


def seed_from_traces() -> int:
    """
    Pre-populate RAG memory from historical agent_traces data.

    The bill_matcher agent writes structured strings to agent_traces:
      input_summary: "company=QuickTrip Fuel amount=45.00 turn=2"
      result:        "matched=Transportation confidence=HIGH"

    This function parses those strings and loads all successful past matches
    into the vector store, so RAG is useful from the first run — not just
    going forward.

    Returns:
        Number of memories successfully seeded.
    """
    _init()

    from database import get_connection

    with get_connection() as conn:
        rows = conn.execute("""
            SELECT input_summary, result
            FROM agent_traces
            WHERE agent_name = 'bill_matcher'
              AND result LIKE 'matched=%'
              AND result NOT LIKE '%confidence=LOW%'
              AND result NOT LIKE '%no_match%'
              AND pipeline_run_id NOT LIKE 'eval_%'
              AND pipeline_run_id NOT LIKE 'test-%'
        """).fetchall()

    count = 0
    for input_summary, result in rows:
        # Parse: "company=Quick Trip amount=45.00 turn=2"
        company_match = re.search(r'company=(.+?) (?:amount|turn)', input_summary)
        # Parse: "matched=Transportation confidence=HIGH"
        bill_match = re.search(r'matched=(.+?) confidence=(\w+)', result)

        if company_match and bill_match:
            company_name = company_match.group(1).strip()
            bill_name    = bill_match.group(1).strip()
            confidence   = bill_match.group(2).strip()

            if company_name and bill_name and confidence in ("HIGH", "MEDIUM"):
                add_payment_memory(company_name, bill_name, confidence)
                count += 1

    return count


def clear_memory():
    """
    Delete all stored memories and recreate the collection.
    Used for testing/resetting the RAG store.
    """
    global _collection
    _init()

    _client.delete_collection(COLLECTION_NAME)
    _collection = _client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
