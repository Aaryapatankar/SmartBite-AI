# Architecture
**Layers:** Frontend (Streamlit, only talks HTTP) -> API (FastAPI + Pydantic validation) -> Services (`data.py` dataset + calculations, `tools.py` 8 tools, `db.py` SQLite) -> AI (`llm.py`, `rag.py`, `agent.py`).

**Key decisions**
- Tools are plain functions returning `{ok, data, label}`; the UI pages call them directly via the API (fast, deterministic), and the agent calls the same functions through LangChain wrappers. One implementation, two entry points.
- Nutrition and cost are computed from ingredient grams x per-100g values; they are never produced by the LLM.
- The LLM is only used for: intent/RAG routing, tool selection, final answers, custom recipe generation. No LLM key means a clear 503 error, never a fake answer.
- Embeddings use ChromaDB's local default model so no extra paid API is needed.
- SQLite stores recipes (seeded), preferences, saved recipes, meal plans, nutrition calculations and chat history.

**LangGraph nodes:** understand, retrieve, plan_tools, execute_tools, validate, respond. Conditional edges: understand -> retrieve (if RAG needed) else plan_tools; plan_tools -> execute_tools (if tools chosen) else respond.

**Value labels:** dataset | calculated estimate | general guidance | AI suggestion.
