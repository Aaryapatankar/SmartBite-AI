"""Loads the ingredient and recipe datasets and CALCULATES nutrition and cost.

Values in data/ingredients.csv are APPROXIMATE (not lab verified). Everything computed
here is therefore a "calculated estimate".
"""
import csv
import json
from functools import lru_cache

from backend.config import DATA_DIR

NON_VEG_CATEGORY = "non-veg"


@lru_cache(maxsize=1)
def ingredients() -> dict:
    """Return {ingredient_name: {kcal, protein, carbs, fat, price_per_kg, diet}} per 100 g."""
    out = {}
    with open(DATA_DIR / "ingredients.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            out[row["name"].strip().lower()] = {
                "kcal": float(row["kcal"]), "protein": float(row["protein"]),
                "carbs": float(row["carbs"]), "fat": float(row["fat"]),
                "price_per_kg": float(row["price_per_kg"]), "diet": row["diet"],
            }
    return out


def _enrich(raw: dict) -> dict:
    ing = ingredients()
    breakdown, tot = [], {"kcal": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0, "cost": 0.0}
    for name, grams in raw["ingredients"]:
        i = ing[name]
        row = {"ingredient": name, "grams": grams}
        for k in ("kcal", "protein", "carbs", "fat"):
            row[k] = round(i[k] * grams / 100, 1)
        row["cost"] = round(i["price_per_kg"] * grams / 1000, 2)
        breakdown.append(row)
        for k in tot:
            tot[k] += row[k] if k != "cost" else row["cost"]
    s = raw["servings"]
    diet = "non-veg" if any(ing[n]["diet"] == NON_VEG_CATEGORY for n, _ in raw["ingredients"]) else "veg"
    rec = dict(raw)
    rec.update({
        "diet": diet,
        "total": {k: round(v, 1) for k, v in tot.items()},
        "per_serving": {
            "calories": round(tot["kcal"] / s), "protein": round(tot["protein"] / s, 1),
            "carbs": round(tot["carbs"] / s, 1), "fat": round(tot["fat"] / s, 1),
        },
        "cost_per_serving": round(tot["cost"] / s, 1),
        "total_cost": round(tot["cost"], 1),
        "breakdown": breakdown,
    })
    return rec


@lru_cache(maxsize=1)
def recipes() -> list:
    with open(DATA_DIR / "recipes.json", encoding="utf-8") as f:
        return [_enrich(r) for r in json.load(f)]


def get_recipe(ref):
    """Find a recipe by numeric id or by (partial, case-insensitive) name."""
    if isinstance(ref, int) or (isinstance(ref, str) and ref.strip().isdigit()):
        rid = int(ref)
        return next((r for r in recipes() if r["id"] == rid), None)
    if isinstance(ref, str) and ref.strip():
        q = ref.strip().lower()
        exact = [r for r in recipes() if r["name"].lower() == q]
        part = [r for r in recipes() if q in r["name"].lower()]
        return (exact or part or [None])[0]
    return None


def summary(r: dict) -> dict:
    return {"id": r["id"], "name": r["name"], "diet": r["diet"], "meals": r["meals"],
            "cuisine": r["cuisine"], "time_min": r["time_min"], "servings": r["servings"],
            "calories": r["per_serving"]["calories"], "protein": r["per_serving"]["protein"],
            "cost_per_serving": r["cost_per_serving"]}
