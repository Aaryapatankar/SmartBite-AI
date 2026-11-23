"""FastAPI backend. Run:  python -m uvicorn backend.main:app --port 8000   (docs at /docs)"""
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from backend.ai.llm import LLMUnavailable, get_llm, text_of
from backend.services import data, db, tools

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("smartbite.api")
Diet = str


@asynccontextmanager
async def lifespan(app):
    db.init_db()
    yield


app = FastAPI(title="SmartBite AI API", version="1.0", lifespan=lifespan)


def run(fn, **kw):
    """Run a tool; convert a tool error into HTTP 400."""
    res = fn(**kw)
    if not res["ok"]:
        raise HTTPException(400, res["error"])
    return res


class SearchReq(BaseModel):
    query: str = Field("", max_length=100)
    diet: Diet = "any"
    meal: str = "any"
    max_time: Optional[int] = Field(None, gt=0, le=1000)
    max_cost_per_serving: Optional[float] = Field(None, gt=0)


class MatchReq(BaseModel):
    ingredients: list[str] = Field(..., min_length=1, max_length=30)
    diet: Diet = "any"


class NutritionReq(BaseModel):
    recipe: str = Field(..., min_length=1)
    servings: float = Field(1, gt=0, le=50)


class CalorieReq(BaseModel):
    items: list[dict] = Field(..., min_length=1, max_length=40)


class BudgetReq(BaseModel):
    recipe: str = Field(..., min_length=1)
    servings: Optional[float] = Field(None, gt=0, le=50)
    budget: Optional[float] = Field(None, gt=0)


class PlanReq(BaseModel):
    days: int = Field(1, ge=1, le=7)
    diet: Diet = "any"
    budget_per_day: Optional[float] = Field(None, gt=0)
    daily_calorie_target: Optional[float] = Field(None, gt=0)


class SubReq(BaseModel):
    ingredient: str = Field(..., min_length=1, max_length=50)
    diet: Diet = "any"


class RecReq(BaseModel):
    goal: str = "balanced"
    diet: Diet = "any"
    meal: str = "any"
    max_cost_per_serving: Optional[float] = Field(None, gt=0)
    min_protein: Optional[float] = Field(None, gt=0)
    top_n: int = Field(3, ge=1, le=10)


class ChatReq(BaseModel):
    question: str = Field(..., min_length=2, max_length=1000)


class GenReq(BaseModel):
    ingredients: list[str] = Field(..., min_length=1, max_length=20)
    diet: Diet = "veg"
    max_time: int = Field(30, gt=0, le=240)
    notes: str = Field("", max_length=300)


@app.get("/api/health")
def health():
    return {"status": "ok", "recipes": len(data.recipes())}


@app.get("/api/ingredients")
def list_ingredients():
    return sorted(data.ingredients())


@app.get("/api/recipes")
def all_recipes():
    return [data.summary(r) for r in data.recipes()]


@app.get("/api/recipes/{ref}")
def one_recipe(ref: str):
    r = data.get_recipe(ref)
    if not r:
        raise HTTPException(404, "Recipe not found")
    return r


@app.post("/api/recipes/search")
def search(req: SearchReq):
    return run(tools.recipe_search, **req.model_dump())


@app.post("/api/recipes/match")
def match(req: MatchReq):
    return run(tools.ingredient_match, **req.model_dump())


@app.post("/api/nutrition")
def nutrition(req: NutritionReq):
    res = run(tools.nutrition_calculator, **req.model_dump())
    r = data.get_recipe(req.recipe)
    db.log_nutrition(r["id"], req.servings, res["data"]["total"])
    return res


@app.post("/api/calories")
def calories(req: CalorieReq):
    return run(tools.calorie_calculator, **req.model_dump())


@app.post("/api/budget")
def budget(req: BudgetReq):
    return run(tools.budget_estimator, **req.model_dump())


@app.post("/api/mealplan")
def mealplan(req: PlanReq):
    return run(tools.meal_planner, **req.model_dump())


@app.post("/api/mealplan/save")
def save_plan(plan: dict, title: str = "My meal plan"):
    return {"id": db.save_meal_plan(title, plan)}


@app.get("/api/mealplan/saved")
def saved_plans():
    return db.list_meal_plans()


@app.post("/api/substitute")
def substitute(req: SubReq):
    return run(tools.food_substitution, **req.model_dump())


@app.post("/api/recommend")
def recommend(req: RecReq):
    return run(tools.recipe_recommender, **req.model_dump())


@app.post("/api/saved/{recipe_id}")
def save(recipe_id: int):
    if not data.get_recipe(recipe_id):
        raise HTTPException(404, "Recipe not found")
    db.save_recipe(recipe_id)
    return {"saved": recipe_id}


@app.get("/api/saved")
def saved():
    return db.list_saved()


@app.get("/api/preferences")
def get_prefs():
    return db.get_prefs()


@app.post("/api/preferences")
def set_prefs(prefs: dict[str, str]):
    for k, v in prefs.items():
        db.set_pref(k[:50], v[:200])
    return db.get_prefs()


@app.get("/api/history")
def history():
    return db.get_history()


@app.get("/api/rag/status")
def rag_status():
    from backend.ai import rag
    return rag.status()


@app.post("/api/rag/rebuild")
def rag_rebuild():
    from backend.ai import rag
    try:
        rag.get_store(rebuild=True)
    except rag.RagUnavailable as e:
        raise HTTPException(503, str(e))
    return rag.status()


@app.post("/api/chat")
def chat(req: ChatReq):
    try:
        from backend.ai.agent import run_agent
        out = run_agent(req.question)
    except LLMUnavailable as e:
        raise HTTPException(503, str(e))
    except ImportError as e:
        raise HTTPException(503, f"AI dependencies missing: {e}")
    except Exception as e:
        log.exception("agent failed")
        raise HTTPException(502, f"The AI model returned an error: {e}")
    db.add_chat(req.question, out["answer"], [t["tool"] for t in out["tools_used"]])
    return out


@app.post("/api/ai/generate-recipe")
def generate_recipe(req: GenReq):
    """Generative AI custom recipe. Output is an AI SUGGESTION, not verified data."""
    try:
        llm = get_llm()
        msg = llm.invoke(f"Create one {req.diet} Indian recipe using mainly: {', '.join(req.ingredients)}. "
                         f"Max {req.max_time} minutes. Notes: {req.notes or 'none'}. Give: title, ingredients with quantities, "
                         "numbered steps, and a safety tip. Be concise. Do not state exact nutrition numbers.")
    except LLMUnavailable as e:
        raise HTTPException(503, str(e))
    except Exception as e:
        log.exception("generation failed")
        raise HTTPException(502, f"The AI model returned an error: {e}")
    return {"recipe": text_of(msg), "label": "AI-generated suggestion (not verified)"}
