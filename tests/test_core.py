"""Core tests (no third-party packages needed): data, tools, database. Run: python -m unittest discover tests"""
import csv
import json
import os
import tempfile
import unittest

from backend.config import DATA_DIR
from backend.services import data, db, tools


class TestData(unittest.TestCase):
    def test_files_are_valid(self):
        json.load(open(DATA_DIR / "recipes.json", encoding="utf-8"))
        self.assertGreater(len(list(csv.DictReader(open(DATA_DIR / "ingredients.csv")))), 10)

    def test_every_recipe_ingredient_exists_and_values_positive(self):
        for r in data.recipes():
            for name, g in r["ingredients"]:
                self.assertIn(name, data.ingredients())
                self.assertGreater(g, 0)
            self.assertGreater(r["per_serving"]["calories"], 0)
            self.assertGreater(r["cost_per_serving"], 0)
            self.assertGreaterEqual(len(r["steps"]), 3)

    def test_both_diets_and_all_meals_present(self):
        self.assertTrue({r["diet"] for r in data.recipes()} == {"veg", "non-veg"})
        for m in ("breakfast", "lunch", "snack", "dinner"):
            self.assertTrue(any(m in r["meals"] for r in data.recipes()))


class TestTools(unittest.TestCase):
    def test_search_empty_returns_all(self):
        self.assertEqual(len(tools.recipe_search()["data"]), len(data.recipes()))

    def test_search_text_and_no_result(self):
        self.assertTrue(any(r["name"] == "Palak Paneer" for r in tools.recipe_search("paneer")["data"]))
        self.assertEqual(tools.recipe_search("zzzzqq")["data"], [])

    def test_vegetarian_filter(self):
        res = tools.recipe_search(diet="veg")["data"]
        self.assertTrue(res and all(r["diet"] == "veg" for r in res))

    def test_non_vegetarian_filter(self):
        res = tools.recipe_search(diet="non-veg")["data"]
        self.assertTrue(res and all(r["diet"] == "non-veg" for r in res))

    def test_invalid_inputs(self):
        self.assertFalse(tools.recipe_search(diet="vegan")["ok"])
        self.assertFalse(tools.recipe_search(meal="brunch")["ok"])
        self.assertFalse(tools.recipe_search(max_time=-5)["ok"])
        self.assertFalse(tools.recipe_search(max_time="abc")["ok"])

    def test_match_ingredients(self):
        res = tools.ingredient_match(["paneer", "spinach", "onion", "tomato"])
        self.assertTrue(res["ok"])
        self.assertEqual(res["data"]["matches"][0]["name"], "Palak Paneer")

    def test_match_empty_and_invalid(self):
        self.assertFalse(tools.ingredient_match([])["ok"])
        self.assertFalse(tools.ingredient_match(["unobtainium"])["ok"])
        self.assertFalse(tools.ingredient_match("paneer")["ok"])
        self.assertFalse(tools.ingredient_match([""])["ok"])

    def test_match_respects_diet(self):
        res = tools.ingredient_match(["chicken", "paneer", "egg"], diet="veg")["data"]["matches"]
        self.assertTrue(all(m["diet"] == "veg" for m in res))

    def test_nutrition_scales_with_servings(self):
        one = tools.nutrition_calculator("Dal Tadka", 1)["data"]["total"]["calories"]
        two = tools.nutrition_calculator("Dal Tadka", 2)["data"]["total"]["calories"]
        self.assertAlmostEqual(two, one * 2, delta=2)

    def test_nutrition_validation(self):
        self.assertFalse(tools.nutrition_calculator("Dal Tadka", 0)["ok"])
        self.assertFalse(tools.nutrition_calculator("Dal Tadka", 1000)["ok"])
        self.assertFalse(tools.nutrition_calculator("No Such Dish", 1)["ok"])

    def test_calorie_calculator_known_value(self):
        res = tools.calorie_calculator([{"ingredient": "oil", "grams": 10}])
        self.assertEqual(res["data"]["total"]["kcal"], 88.4)

    def test_calorie_calculator_errors(self):
        self.assertFalse(tools.calorie_calculator([])["ok"])
        self.assertFalse(tools.calorie_calculator([{"ingredient": "moonrock", "grams": 5}])["ok"])
        self.assertFalse(tools.calorie_calculator([{"ingredient": "rice", "grams": -1}])["ok"])

    def test_budget_constraints(self):
        cheap = tools.budget_estimator("Paneer Bhurji", 2, 1000)["data"]
        self.assertTrue(cheap["within_budget"])
        tight = tools.budget_estimator("Paneer Bhurji", 2, 10)["data"]
        self.assertFalse(tight["within_budget"])
        self.assertTrue(tight["cheaper_alternatives"])
        self.assertFalse(tools.budget_estimator("Paneer Bhurji", budget=-1)["ok"])

    def test_meal_planner(self):
        plan = tools.meal_planner(7, "veg")["data"]["days"]
        self.assertEqual(len(plan), 7)
        for d in plan:
            self.assertEqual(set(d["meals"]), {"breakfast", "lunch", "snack", "dinner"})
            self.assertTrue(all(m["diet"] == "veg" for m in d["meals"].values()))
        self.assertFalse(tools.meal_planner(0)["ok"])
        self.assertFalse(tools.meal_planner(8)["ok"])

    def test_meal_planner_budget_swaps_to_cheaper(self):
        free = tools.meal_planner(1, "veg")["data"]["days"][0]["cost"]
        capped = tools.meal_planner(1, "veg", free - 5)["data"]["days"][0]["cost"]
        self.assertLessEqual(capped, free)

    def test_substitution(self):
        self.assertTrue(tools.food_substitution("paneer")["data"]["substitutes"])
        self.assertEqual(tools.food_substitution("dragonfruit")["data"]["substitutes"], [])
        self.assertFalse(tools.food_substitution("")["ok"])

    def test_recommender(self):
        top = tools.recipe_recommender("high-protein", "veg")["data"]["recommendations"][0]
        self.assertEqual(top["name"], "Paneer Bhurji")
        self.assertFalse(tools.recipe_recommender("fastest")["ok"])
        self.assertEqual(tools.recipe_recommender(max_cost_per_serving=1)["data"]["recommendations"], [])

    def test_paneer_dinner_under_100(self):
        res = tools.recipe_recommender("high-protein", "veg", "dinner", max_cost_per_serving=100)["data"]["recommendations"]
        self.assertTrue(res and all(r["cost_per_serving"] <= 100 for r in res))

    def test_registry_has_all_eight(self):
        self.assertEqual(len(tools.REGISTRY), 8)


class TestDb(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SMARTBITE_DB"] = os.path.join(self.tmp.name, "t.db")
        db.init_db()

    def tearDown(self):
        os.environ.pop("SMARTBITE_DB", None)
        self.tmp.cleanup()

    def test_prefs_saved_plans_history(self):
        db.set_pref("diet", "veg")
        self.assertEqual(db.get_prefs()["diet"], "veg")
        db.save_recipe(1)
        db.save_recipe(1)
        self.assertEqual(len(db.list_saved()), 1)
        pid = db.save_meal_plan("t", {"a": 1})
        self.assertEqual(db.list_meal_plans()[0]["id"], pid)
        db.add_chat("q", "a", ["recipe_search"])
        self.assertEqual(db.get_history()[0]["tools"], ["recipe_search"])
        db.log_nutrition(1, 2, {"calories": 5})


if __name__ == "__main__":
    unittest.main()
