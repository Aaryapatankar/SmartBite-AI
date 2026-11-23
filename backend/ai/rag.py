"""RAG pipeline: load -> clean -> chunk -> embed -> store (ChromaDB) -> retrieve.

Documents: data/knowledge/*.txt|md|pdf, data/ingredients.csv, and one text card per recipe.
Embeddings: ChromaDB's default local model (all-MiniLM-L6-v2, ONNX). It is downloaded on first use,
so the first index build needs internet access once.
"""
import logging
import re

from backend.config import CHROMA_DIR, DATA_DIR, KNOWLEDGE_DIR
from backend.services import data

log = logging.getLogger("smartbite.rag")
COLLECTION = "smartbite_kb"
_store = None


class RagUnavailable(RuntimeError):
    """Raised when the vector store cannot be built or used."""


def clean(text: str) -> str:
    return re.sub(r"[ \t]+", " ", re.sub(r"\n{3,}", "\n\n", text)).strip()


def recipe_cards():
    """Turn each recipe into a text document (nutrition is labelled as calculated estimate)."""
    from langchain_core.documents import Document
    docs = []
    for r in data.recipes():
        ps = r["per_serving"]
        text = (f"Recipe: {r['name']} ({r['diet']}, {r['cuisine']}). Meals: {', '.join(r['meals'])}. Time: {r['time_min']} min. "
                f"Makes {r['servings']} servings. Ingredients: {', '.join(f'{n} {g} g' for n, g in r['ingredients'])}. "
                f"Steps: {' '.join(r['steps'])} Estimated per serving (calculated from approximate values): "
                f"{ps['calories']} kcal, {ps['protein']} g protein, {ps['carbs']} g carbs, {ps['fat']} g fat. "
                f"Estimated cost per serving: INR {r['cost_per_serving']}.")
        docs.append(Document(page_content=text, metadata={"source": f"recipe:{r['name']}", "type": "recipe"}))
    return docs


def load_documents():
    """Load text, markdown, PDF and CSV files, then add recipe cards."""
    try:
        from langchain_community.document_loaders import CSVLoader, PyPDFLoader, TextLoader
    except ImportError as e:
        raise RagUnavailable("langchain-community is not installed.") from e
    docs = []
    if KNOWLEDGE_DIR.exists():
        for p in sorted(KNOWLEDGE_DIR.iterdir()):
            try:
                if p.suffix.lower() in {".txt", ".md"}:
                    docs += TextLoader(str(p), encoding="utf-8").load()
                elif p.suffix.lower() == ".pdf":
                    docs += PyPDFLoader(str(p)).load()
                elif p.suffix.lower() == ".csv":
                    docs += CSVLoader(str(p), encoding="utf-8").load()
            except Exception as e:  # a bad file must not break the whole index
                log.warning("Skipping %s: %s", p.name, e)
    docs += CSVLoader(str(DATA_DIR / "ingredients.csv"), encoding="utf-8").load()
    docs += recipe_cards()
    for d in docs:
        d.page_content = clean(d.page_content)
        d.metadata["source"] = str(d.metadata.get("source", "unknown")).replace("\\", "/").split("/")[-1]
    return [d for d in docs if d.page_content]


def chunk(docs):
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    return RecursiveCharacterTextSplitter(chunk_size=600, chunk_overlap=80).split_documents(docs)


def _embeddings():
    from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
    from langchain_core.embeddings import Embeddings

    class ChromaDefault(Embeddings):
        def __init__(self):
            self.fn = DefaultEmbeddingFunction()

        def embed_documents(self, texts):
            return [[float(x) for x in v] for v in self.fn(texts)]

        def embed_query(self, text):
            return self.embed_documents([text])[0]

    return ChromaDefault()


def get_store(rebuild: bool = False):
    global _store
    if _store is not None and not rebuild:
        return _store
    try:
        from langchain_chroma import Chroma
        store = Chroma(collection_name=COLLECTION, embedding_function=_embeddings(), persist_directory=str(CHROMA_DIR))
        if rebuild:
            store.delete_collection()
            store = Chroma(collection_name=COLLECTION, embedding_function=_embeddings(), persist_directory=str(CHROMA_DIR))
        if store._collection.count() == 0:
            chunks = chunk(load_documents())
            log.info("Indexing %d chunks", len(chunks))
            store.add_documents(chunks)
        _store = store
        return store
    except RagUnavailable:
        raise
    except Exception as e:
        raise RagUnavailable(f"Could not build the vector store: {e}") from e


def retrieve(query: str, k: int = 4):
    """Return top-k chunks as [{text, source, distance}] (lower distance = more similar)."""
    if not query or not query.strip():
        return []
    res = get_store().similarity_search_with_score(query.strip(), k=k)
    return [{"text": d.page_content, "source": d.metadata.get("source", "unknown"), "distance": round(float(s), 3)} for d, s in res]


def status() -> dict:
    try:
        return {"available": True, "chunks": get_store()._collection.count()}
    except RagUnavailable as e:
        return {"available": False, "error": str(e)}
