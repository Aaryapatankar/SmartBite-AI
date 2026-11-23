# SmartBite AI
**An Intelligent Recipe Recommendation and Food Nutrition Assistant using Generative AI, RAG and Tool Calling.**

## Honest status (read first)
| Part | Status |
|---|---|
| Dataset, SQLite, 8 tools, services (pure Python) | **Tested**: 23 unit tests passed in the build environment |
| FastAPI backend, Streamlit UI, ChromaDB RAG, LangGraph agent, Gemini calls | **Written but NOT executed** in the build environment (no internet, packages could not be installed). Their tests exist in `tests/` but were *skipped* there |
| `run_windows.bat` | **Not run** (built on Linux). Written carefully, but expect that you may need to fix small issues |

So: run the tests on your PC first (below). If something fails, paste the error into Claude and ask for a fix.

## Quick start (Windows 10/11)
1. Install Python 3.10 to 3.12 (tick "Add python.exe to PATH").
2. Extract the ZIP, open the `SmartBite_AI` folder in VS Code.
3. Double-click `run_windows.bat`. It creates `.venv`, installs packages, creates `.env`, starts backend (port 8000) and frontend (port 8501) and opens the browser.
4. Stop with `stop_windows.bat`.

**AI features need a key:** put a free Gemini key in `.env` (`GEMINI_API_KEY=...`, from https://aistudio.google.com/apikey). Free tiers have rate limits. Without a key, the AI assistant and AI recipe generator show a clear message; the recipe, nutrition, budget and meal-plan pages still work. Local alternative: install Ollama and set `LLM_PROVIDER=ollama`.
**RAG:** the first AI chat builds the vector index and downloads a small embedding model (internet needed once).

## Problem and objectives
People struggle to decide what to cook from available ingredients, how healthy it is and what it costs. SmartBite AI finds Indian recipes, estimates nutrition and cost, plans meals and answers food questions with grounded answers.

## Features
Find recipes by ingredients/diet/time/budget; nutrition analyzer; budget planner with cheaper alternatives; daily/weekly meal planner; AI food assistant (RAG + tools + sources); AI custom recipe generator; saved recipes, plans and chat history in SQLite.

## Technology stack
Python, FastAPI, Pydantic, Streamlit + custom CSS, LangChain, LangGraph, ChromaDB, SQLite, Gemini (or Ollama).

## Architecture
```
Streamlit UI  --HTTP-->  FastAPI  --> services (data, tools, db)
                            |
                            +--> LangGraph agent: understand -> retrieve (RAG) -> plan_tools -> execute_tools -> validate -> respond
                                         |                |                |
                                       Gemini        ChromaDB         8 Python tools
```
See `docs/ARCHITECTURE.md`.

## Folder structure
```
backend/  main.py (API) | config.py | services/ (data, tools, db) | ai/ (llm, rag, agent)
frontend/ app.py | views.py | api.py | styles.css
data/     recipes.json | ingredients.csv | knowledge/*.txt (add your own .txt .md .pdf .csv here)
tests/    test_core.py | test_api.py | test_ai.py
docs/     ARCHITECTURE.md | VIVA_PREP.md
```

## Run manually
```
python -m venv .venv && .venv\Scripts\activate && pip install -r requirements.txt
python -m uvicorn backend.main:app --port 8000
python -m streamlit run frontend/app.py
```
API docs: http://127.0.0.1:8000/docs

## API summary
`GET /api/health, /api/ingredients, /api/recipes, /api/recipes/{id}, /api/saved, /api/history, /api/rag/status, /api/preferences` ·
`POST /api/recipes/search, /api/recipes/match, /api/nutrition, /api/calories, /api/budget, /api/mealplan, /api/substitute, /api/recommend, /api/chat, /api/ai/generate-recipe, /api/rag/rebuild, /api/saved/{id}, /api/preferences`.
Validation errors return 422, tool/input errors 400, missing AI key 503.

## RAG
Loaders (Text, PDF, CSV) -> cleaning -> `RecursiveCharacterTextSplitter` (600/80) -> Chroma default local embeddings -> ChromaDB (persisted in `storage/chroma`) -> similarity search (top 4) -> context with `[S1]` labels -> LLM answer. Sources are shown in the UI. If context is missing, the prompt tells the model to say so.

## Tool calling
The 8 tools in `backend/services/tools.py` are wrapped as LangChain tools in `agent.py` and bound to the LLM, which chooses which to call. Executed tools and arguments are displayed in the assistant page.

## Agent workflow
`understand` (LLM decides intent and whether RAG is needed) -> `retrieve` -> `plan_tools` (LLM tool selection) -> `execute_tools` -> `validate` -> `respond`.

## Data honesty
- `ingredients.csv` values are **approximate typical values typed in by the author, not verified**. Check against IFCT / USDA FoodData Central before quoting them.
- Prices are rough Indian retail averages.
- Nutrition and cost shown are **calculated estimates**; AI recipe text is an **AI suggestion**. Not medical advice.
- Food images are not included (emoji and gradients are used instead).

## Testing
`python -m unittest discover -s tests -t . -v` (or `pytest`). Results in the build environment: 37 tests, 23 passed, 14 skipped (API/RAG/agent tests need the installed packages). Set `RUN_RAG_INTEGRATION=1` to also run real retrieval.

## Limitations
15 recipes only; Indian cuisine only; approximate data; one serving of each recipe per meal in plans; the meal planner is rule-based (tool), AI commentary comes from the assistant; unpinned dependency versions; launcher untested.

## Future enhancements
More recipes/cuisines (the `cuisine` field and dataset format already allow it), verified nutrition tables, real food images, user accounts, pantry tracking, pinned dependency versions.
