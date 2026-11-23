"""SQLite persistence: recipes, preferences, saved recipes, meal plans, nutrition logs, chat history."""
import json
import sqlite3
from contextlib import contextmanager

from backend.config import db_path
from backend.services import data

SCHEMA = """
CREATE TABLE IF NOT EXISTS recipes (id INTEGER PRIMARY KEY, name TEXT, diet TEXT, cuisine TEXT,
    time_min INTEGER, servings INTEGER, calories INTEGER, protein REAL, cost_per_serving REAL);
CREATE TABLE IF NOT EXISTS preferences (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS saved_recipes (recipe_id INTEGER PRIMARY KEY, saved_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS meal_plans (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, plan_json TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS nutrition_calcs (id INTEGER PRIMARY KEY AUTOINCREMENT, recipe_id INTEGER,
    servings REAL, result_json TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS chat_history (id INTEGER PRIMARY KEY AUTOINCREMENT, question TEXT, answer TEXT,
    tools_json TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
"""


@contextmanager
def conn():
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init_db() -> None:
    """Create tables and (re)seed the recipes table from the dataset."""
    with conn() as c:
        c.executescript(SCHEMA)
        c.execute("DELETE FROM recipes")
        for r in data.recipes():
            s = data.summary(r)
            c.execute("INSERT INTO recipes VALUES (?,?,?,?,?,?,?,?,?)",
                      (s["id"], s["name"], s["diet"], s["cuisine"], s["time_min"], s["servings"],
                       s["calories"], s["protein"], s["cost_per_serving"]))


def set_pref(key: str, value: str) -> None:
    with conn() as c:
        c.execute("INSERT OR REPLACE INTO preferences VALUES (?,?)", (key, value))


def get_prefs() -> dict:
    with conn() as c:
        return {r["key"]: r["value"] for r in c.execute("SELECT * FROM preferences")}


def save_recipe(recipe_id: int) -> None:
    with conn() as c:
        c.execute("INSERT OR IGNORE INTO saved_recipes (recipe_id) VALUES (?)", (recipe_id,))


def list_saved() -> list:
    with conn() as c:
        rows = c.execute("SELECT recipe_id FROM saved_recipes ORDER BY saved_at DESC").fetchall()
    return [data.summary(data.get_recipe(r["recipe_id"])) for r in rows]


def save_meal_plan(title: str, plan: dict) -> int:
    with conn() as c:
        cur = c.execute("INSERT INTO meal_plans (title, plan_json) VALUES (?,?)", (title, json.dumps(plan)))
        return cur.lastrowid


def list_meal_plans() -> list:
    with conn() as c:
        return [{"id": r["id"], "title": r["title"], "created_at": r["created_at"],
                 "plan": json.loads(r["plan_json"])} for r in c.execute("SELECT * FROM meal_plans ORDER BY id DESC")]


def log_nutrition(recipe_id: int, servings: float, result: dict) -> None:
    with conn() as c:
        c.execute("INSERT INTO nutrition_calcs (recipe_id, servings, result_json) VALUES (?,?,?)",
                  (recipe_id, servings, json.dumps(result)))


def add_chat(question: str, answer: str, tools: list) -> None:
    with conn() as c:
        c.execute("INSERT INTO chat_history (question, answer, tools_json) VALUES (?,?,?)",
                  (question, answer, json.dumps(tools)))


def get_history(limit: int = 20) -> list:
    with conn() as c:
        rows = c.execute("SELECT * FROM chat_history ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [{"question": r["question"], "answer": r["answer"], "tools": json.loads(r["tools_json"]),
             "created_at": r["created_at"]} for r in rows]
