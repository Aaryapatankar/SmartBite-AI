"""API tests. Need fastapi + httpx installed (pip install -r requirements.txt); skipped otherwise."""
import os
import tempfile
import unittest

try:
    from fastapi.testclient import TestClient
    from backend.main import app
    HAVE = True
except ImportError:
    HAVE = False


@unittest.skipUnless(HAVE, "fastapi/httpx not installed")
class TestApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        os.environ["SMARTBITE_DB"] = os.path.join(cls.tmp.name, "api.db")
        cls.cm = TestClient(app)
        cls.c = cls.cm.__enter__()  # runs startup (creates the database)

    @classmethod
    def tearDownClass(cls):
        cls.cm.__exit__(None, None, None)
        os.environ.pop("SMARTBITE_DB", None)

    def test_health(self):
        self.assertEqual(self.c.get("/api/health").json()["status"], "ok")

    def test_search_veg(self):
        r = self.c.post("/api/recipes/search", json={"diet": "veg"}).json()
        self.assertTrue(all(x["diet"] == "veg" for x in r["data"]))

    def test_validation_errors(self):
        self.assertEqual(self.c.post("/api/nutrition", json={"recipe": "Dal Tadka", "servings": 0}).status_code, 422)
        self.assertEqual(self.c.post("/api/recipes/match", json={"ingredients": []}).status_code, 422)
        self.assertEqual(self.c.post("/api/recipes/match", json={"ingredients": ["unobtainium"]}).status_code, 400)
        self.assertEqual(self.c.get("/api/recipes/9999").status_code, 404)

    def test_nutrition_and_budget(self):
        self.assertEqual(self.c.post("/api/nutrition", json={"recipe": "Dal Tadka", "servings": 2}).status_code, 200)
        b = self.c.post("/api/budget", json={"recipe": "Dal Tadka", "servings": 2, "budget": 5}).json()
        self.assertFalse(b["data"]["within_budget"])

    def test_chat_without_api_key_is_clear_error(self):
        old = os.environ.pop("GEMINI_API_KEY", None)
        os.environ["LLM_PROVIDER"] = "gemini"
        try:
            r = self.c.post("/api/chat", json={"question": "high protein dinner"})
            self.assertEqual(r.status_code, 503)
            self.assertIn("GEMINI_API_KEY", r.json()["detail"])
        finally:
            os.environ.pop("LLM_PROVIDER", None)
            if old:
                os.environ["GEMINI_API_KEY"] = old

    def test_chat_rejects_empty(self):
        self.assertEqual(self.c.post("/api/chat", json={"question": ""}).status_code, 422)


if __name__ == "__main__":
    unittest.main()
