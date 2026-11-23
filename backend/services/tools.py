"""The 8 callable tools. Plain Python functions with validated inputs and structured outputs.

Every tool returns {"ok": bool, "data": ..., "label": ...} or {"ok": False, "error": "..."}.
`label` tells the user what kind of value this is:
  - "dataset"             : read straight from the dataset
  - "calculated estimate" : computed from approximate ingredient values
  - "general guidance"    : general culinary knowledge, not from the dataset
The LangGraph agent calls these via LangChain tool wrappers (see backend/ai/agent.py).
"""
from backend.services import data

DIETS = {"any", "veg", "non-veg"}
MEALS = {"any", "breakfast", "lunch", "snack", "dinner"}
STAPLES = {"oil", "masala", "ginger-garlic paste", "ghee"}  # assumed to be in every kitchen


class ToolError(ValueError):
    """Raised for invalid tool input; converted into an error result."""


def _ok(payload, label):
    return {"ok": True, "data": payload, "label": label}


def _err(msg):
    return {"ok": False, "error": msg}


def _guard(fn):
    """Turn ToolError into a structured error result so callers never crash."""
    def wrapper(*a, **kw):
        try:
            return fn(*a, **kw)
        except ToolError as e:
            return _err(str(e))
    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    return wrapper


def _diet(diet):
    d = (diet or "any").strip().lower()
    if d not in DIETS:
        raise ToolError(f"diet must be one of {sorted(DIETS)}, got '{diet}'")
    return d


def _pos(value, name, maximum=None, allow_none=True):
    if value is None:
        if allow_none:
            return None
        raise ToolError(f"{name} is required")
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise ToolError(f"{name} must be a number")
    if v <= 0:
        raise ToolError(f"{name} must be greater than 0")
    if maximum and v > maximum:
        raise ToolError(f"{name} must be at most {maximum}")
    return v


def _recipe(ref):
    r = data.get_recipe(ref)
    if r is None:
        raise ToolError(f"Recipe '{ref}' not found. Use recipe_search to see available recipes.")
    return r


def _filter(diet="any", meal="any"):
    meal = (meal or "any").strip().lower()
    if meal not in MEALS:
        raise ToolError(f"meal must be one of {sorted(MEALS)}, got '{meal}'")
    return [r for r in data.recipes()
            if (diet == "any" or r["diet"] == diet) and (meal == "any" or meal in r["meals"])]


def _norm(name):
    n = str(name).strip().lower()
    if n in data.ingredients():
        return n
    if n.endswith("s") and n[:-1] in data.ingredients():
        return n[:-1]
    return n


# ---------------- Tool 1: recipe search ----------------
@_guard
def recipe_search(query="", diet="any", meal="any", max_time=None, max_cost_per_serving=None):
    """Search recipes by text, diet (any/veg/non-veg), meal, max minutes and max cost per serving (INR)."""
    diet = _diet(diet)
    max_time = _pos(max_time, "max_time", 1000)
    max_cost = _pos(max_cost_per_serving, "max_cost_per_serving", 100000)
    q = str(query or "").strip().lower()[:100]
    found = []
    for r in _filter(diet, meal):
        if max_time and r["time_min"] > max_time:
            continue
        if max_cost and r["cost_per_serving"] > max_cost:
            continue
        hay = " ".join([r["name"], r["cuisine"], " ".join(i[0] for i in r["ingredients"])]).lower()
        words = [w for w in q.split() if w]
        score = sum(w in hay for w in words)
        if words and score == 0:
            continue
        found.append((score, r))
    found.sort(key=lambda x: (-x[0], x[1]["cost_per_serving"]))
    return _ok([data.summary(r) for _, r in found], "dataset")


# ---------------- Tool 2: ingredient matching ----------------
@_guard
def ingredient_match(ingredients, diet="any", top_n=5):
    """Rank recipes by how many of the user's ingredients they use. Oil, ghee, masala, ginger-garlic are assumed available."""
    diet = _diet(diet)
    if not isinstance(ingredients, (list, tuple)) or not ingredients:
        raise ToolError("ingredients must be a non-empty list of names")
    have, unknown = set(), []
    for raw in ingredients:
        if not isinstance(raw, str) or not raw.strip() or len(raw) > 50:
            raise ToolError("each ingredient must be a non-empty string up to 50 characters")
        n = _norm(raw)
        (have.add(n) if n in data.ingredients() else unknown.append(raw.strip()))
    if not have:
        raise ToolError(f"None of these ingredients are recognised: {unknown}. Known: {sorted(data.ingredients())}")
    out = []
    for r in _filter(diet):
        needed = {i[0] for i in r["ingredients"]} - STAPLES
        matched = needed & have
        if not matched:
            continue
        out.append({**data.summary(r), "match_pct": round(100 * len(matched) / len(needed)),
                    "matched": sorted(matched), "missing": sorted(needed - have)})
    out.sort(key=lambda x: (-x["match_pct"], len(x["missing"])))
    return _ok({"matches": out[: int(top_n)], "unrecognized": unknown}, "calculated estimate")


# ---------------- Tool 3: nutrition calculator ----------------
@_guard
def nutrition_calculator(recipe, servings=1):
    """Calories, protein, carbs, fat for a number of servings of a recipe (name or id)."""
    r = _recipe(recipe)
    n = _pos(servings, "servings", 50, allow_none=False)
    f = n / r["servings"]
    ps = r["per_serving"]
    return _ok({
        "recipe": r["name"], "servings": n,
        "per_serving": ps,
        "total": {"calories": round(ps["calories"] * n), "protein": round(ps["protein"] * n, 1),
                  "carbs": round(ps["carbs"] * n, 1), "fat": round(ps["fat"] * n, 1)},
        "breakdown": [{**b, **{k: round(b[k] * f, 1) for k in ("kcal", "protein", "carbs", "fat", "cost")},
                       "grams": round(b["grams"] * f)} for b in r["breakdown"]],
    }, "calculated estimate")


# ---------------- Tool 4: calorie calculator ----------------
@_guard
def calorie_calculator(items):
    """Total calories/macros for custom items: [{"ingredient": "paneer", "grams": 100}, ...]."""
    if not isinstance(items, (list, tuple)) or not items:
        raise ToolError("items must be a non-empty list of {ingredient, grams}")
    tot = {"kcal": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0}
    rows, bad = [], []
    for it in items:
        if not isinstance(it, dict):
            raise ToolError("each item must be an object with 'ingredient' and 'grams'")
        name = _norm(it.get("ingredient", ""))
        g = _pos(it.get("grams"), "grams", 5000, allow_none=False)
        info = data.ingredients().get(name)
        if not info:
            bad.append(str(it.get("ingredient")))
            continue
        row = {"ingredient": name, "grams": g, **{k: round(info[k] * g / 100, 1) for k in tot}}
        rows.append(row)
        for k in tot:
            tot[k] += row[k]
    if bad:
        raise ToolError(f"Unknown ingredient(s): {bad}. Known: {sorted(data.ingredients())}")
    split = {"protein_kcal": round(tot["protein"] * 4), "carb_kcal": round(tot["carbs"] * 4), "fat_kcal": round(tot["fat"] * 9)}
    return _ok({"items": rows, "total": {k: round(v, 1) for k, v in tot.items()}, "energy_split": split}, "calculated estimate")


# ---------------- Tool 5: budget estimator ----------------
@_guard
def budget_estimator(recipe, servings=None, budget=None):
    """Estimate cost in INR for a recipe, compare with a budget, and suggest cheaper alternatives."""
    r = _recipe(recipe)
    n = _pos(servings, "servings", 50) or r["servings"]
    b = _pos(budget, "budget", 1000000)
    cost = round(r["cost_per_serving"] * n, 1)
    f = n / r["servings"]
    alts = [data.summary(x) for x in sorted(data.recipes(), key=lambda x: x["cost_per_serving"])
            if x["id"] != r["id"] and x["diet"] == r["diet"] and set(x["meals"]) & set(r["meals"])
            and x["cost_per_serving"] < r["cost_per_serving"]][:3]
    return _ok({"recipe": r["name"], "servings": n, "total_cost": cost, "cost_per_serving": r["cost_per_serving"],
                "budget": b, "within_budget": None if b is None else cost <= b,
                "difference": None if b is None else round(b - cost, 1),
                "breakdown": [{"ingredient": x["ingredient"], "grams": round(x["grams"] * f), "cost": round(x["cost"] * f, 2)} for x in r["breakdown"]],
                "cheaper_alternatives": alts}, "calculated estimate")


# ---------------- Tool 6: meal planner ----------------
@_guard
def meal_planner(days=1, diet="any", budget_per_day=None, daily_calorie_target=None):
    """Build a 1-7 day plan (breakfast, lunch, snack, dinner), optionally within a daily budget."""
    diet = _diet(diet)
    d = int(_pos(days, "days", 7, allow_none=False))
    budget = _pos(budget_per_day, "budget_per_day", 100000)
    target = _pos(daily_calorie_target, "daily_calorie_target", 10000)
    notes, used, plan = [], set(), []
    pools = {}
    for m in ("breakfast", "lunch", "snack", "dinner"):
        pool = sorted(_filter(diet, m), key=lambda r: r["id"])
        if not pool and diet != "any":
            pool = sorted(_filter("any", m), key=lambda r: r["id"])
            notes.append(f"No {diet} {m} recipes; used any-diet recipes for {m}.")
        pools[m] = pool
    for i in range(d):
        meals = {}
        for m, pool in pools.items():
            fresh = [r for r in pool if r["id"] not in used] or pool
            pick = fresh[i % len(fresh)]
            used.add(pick["id"])
            meals[m] = pick
        cost = lambda: sum(r["cost_per_serving"] for r in meals.values())
        if budget:
            for _ in range(4):  # swap the most expensive meal for the cheapest option
                if cost() <= budget:
                    break
                m = max(meals, key=lambda k: meals[k]["cost_per_serving"])
                meals[m] = min(pools[m], key=lambda r: r["cost_per_serving"])
        tot = {k: round(sum(r["per_serving"][k] for r in meals.values()), 1) for k in ("calories", "protein", "carbs", "fat")}
        plan.append({"day": i + 1, "meals": {m: data.summary(r) for m, r in meals.items()},
                     "totals": tot, "cost": round(cost(), 1),
                     "within_budget": None if not budget else cost() <= budget,
                     "meets_calorie_target": None if not target else abs(tot["calories"] - target) <= 0.15 * target})
    if budget and any(p["within_budget"] is False for p in plan):
        notes.append("Some days exceed the budget even with the cheapest options.")
    return _ok({"days": plan, "notes": notes, "servings_note": "One serving of each recipe per meal."}, "calculated estimate")


# ---------------- Tool 7: food substitution ----------------
SUBS = {
    "paneer": [("tofu", "veg", "Lower fat, similar protein; milder flavour."), ("soya chunks", "veg", "Very high protein; soak first.")],
    "ghee": [("oil", "veg", "Cheaper; less aroma."), ("butter", "veg", "Similar richness.")],
    "curd": [("hung curd", "veg", "Thicker."), ("coconut yogurt", "veg", "Dairy-free; flavour changes.")],
    "milk": [("soy milk", "veg", "Dairy-free."), ("almond milk", "veg", "Lower protein.")],
    "chicken": [("paneer", "veg", "Vegetarian protein swap."), ("soya chunks", "veg", "Meaty texture.")],
    "egg": [("besan paste", "veg", "Binds like egg in chilla or batter."), ("tofu scramble", "veg", "Good for bhurji.")],
    "fish": [("paneer", "veg", "Vegetarian option."), ("chicken", "non-veg", "Different flavour and cooking time.")],
    "rice": [("millets", "veg", "More fibre."), ("quinoa", "veg", "More protein.")],
    "atta": [("jowar flour", "veg", "Gluten free."), ("multigrain atta", "veg", "More fibre.")],
    "potato": [("sweet potato", "veg", "More fibre; sweeter."), ("cauliflower", "veg", "Lower carbs.")],
    "sugar": [("jaggery", "veg", "Less refined; still adds calories.")],
    "oil": [("ghee", "veg", "More flavour, costs more.")],
}


@_guard
def food_substitution(ingredient, diet="any"):
    """Suggest substitutes for an ingredient (general culinary guidance)."""
    diet = _diet(diet)
    if not isinstance(ingredient, str) or not ingredient.strip():
        raise ToolError("ingredient must be a non-empty string")
    key = _norm(ingredient)
    opts = [{"substitute": s, "diet": d, "note": n} for s, d, n in SUBS.get(key, []) if diet == "any" or d == diet or d == "veg" and diet == "non-veg"]
    return _ok({"ingredient": key, "substitutes": opts,
                "message": "" if opts else f"No substitution stored for '{key}'. Known: {sorted(SUBS)}"}, "general guidance")


# ---------------- Tool 8: recipe recommender ----------------
@_guard
def recipe_recommender(goal="balanced", diet="any", meal="any", max_cost_per_serving=None, min_protein=None, top_n=3):
    """Recommend recipes for a goal: high-protein, low-calorie, budget or balanced."""
    goal = (goal or "balanced").strip().lower()
    if goal not in {"high-protein", "low-calorie", "budget", "balanced"}:
        raise ToolError("goal must be one of: high-protein, low-calorie, budget, balanced")
    diet = _diet(diet)
    max_cost = _pos(max_cost_per_serving, "max_cost_per_serving", 100000)
    minp = _pos(min_protein, "min_protein", 500)
    pool = [r for r in _filter(diet, meal) if (not max_cost or r["cost_per_serving"] <= max_cost)
            and (not minp or r["per_serving"]["protein"] >= minp)]
    keys = {"high-protein": lambda r: -r["per_serving"]["protein"], "low-calorie": lambda r: r["per_serving"]["calories"],
            "budget": lambda r: r["cost_per_serving"], "balanced": lambda r: -r["per_serving"]["protein"] / max(r["per_serving"]["calories"], 1)}
    pool.sort(key=keys[goal])
    return _ok({"goal": goal, "recommendations": [data.summary(r) for r in pool[: int(top_n)]],
                "message": "" if pool else "No recipe matches these constraints."}, "calculated estimate")


REGISTRY = {f.__name__: f for f in (recipe_search, ingredient_match, nutrition_calculator, calorie_calculator,
                                     budget_estimator, meal_planner, food_substitution, recipe_recommender)}
