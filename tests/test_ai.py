"""RAG and agent tests. Skipped automatically if LangChain/LangGraph are not installed.

The agent test uses a STUB language model to verify the graph wiring (nodes, routing, tool execution,
validation). It does NOT test the quality of a real model. The retrieval test needs the embedding model
download, so it only runs when RUN_RAG_INTEGRATION=1.
"""
import os
import unittest
from unittest import mock

try:
    import langchain_core, langgraph  # noqa: F401
    HAVE_AGENT = True
except ImportError:
    HAVE_AGENT = False
try:
    import langchain_community, langchain_text_splitters  # noqa: F401
    HAVE_RAG = True
except ImportError:
    HAVE_RAG = False


@unittest.skipUnless(HAVE_RAG, "langchain-community not installed")
class TestRagPipeline(unittest.TestCase):
    def test_load_clean_chunk(self):
        from backend.ai import rag
        docs = rag.load_documents()
        names = {d.metadata["source"] for d in docs}
        self.assertIn("food_safety.txt", names)
        self.assertIn("ingredients.csv", names)
        self.assertTrue(any(n.startswith("recipe:") for n in names))
        chunks = rag.chunk(docs)
        self.assertGreater(len(chunks), len(names))
        self.assertTrue(all(len(c.page_content) <= 700 for c in chunks))

    def test_missing_docs_folder_is_handled(self):
        from backend.ai import rag
        with mock.patch.object(rag, "KNOWLEDGE_DIR", rag.KNOWLEDGE_DIR / "does_not_exist"):
            self.assertTrue(rag.load_documents())  # still has ingredients + recipe cards

    def test_empty_query(self):
        from backend.ai import rag
        self.assertEqual(rag.retrieve("   "), [])

    @unittest.skipUnless(os.getenv("RUN_RAG_INTEGRATION") == "1", "set RUN_RAG_INTEGRATION=1 (downloads embedding model)")
    def test_retrieval_finds_safety_doc(self):
        from backend.ai import rag
        res = rag.retrieve("safe temperature for cooking chicken", k=3)
        self.assertTrue(any("food_safety" in r["source"] for r in res))


@unittest.skipUnless(HAVE_AGENT, "langgraph not installed")
class TestAgentWorkflow(unittest.TestCase):
    def _fake(self, needs_rag, calls):
        from langchain_core.messages import AIMessage

        class Fake:
            def __init__(s, bound=False):
                s.bound = bound
            def bind_tools(s, _):
                return Fake(True)
            def invoke(s, messages):
                first = messages[0].content
                if "Classify" in first:
                    return AIMessage(content='{"intent":"recipe","needs_rag":%s}' % str(needs_rag).lower())
                if s.bound:
                    return AIMessage(content="", tool_calls=[{"name": n, "args": a, "id": str(i)} for i, (n, a) in enumerate(calls)])
                return AIMessage(content="final answer")
        return Fake()

    def test_full_path_with_rag_and_tools(self):
        from backend.ai import agent
        fake_ctx = [{"text": "Paneer is high in protein.", "source": "nutrition_basics.txt", "distance": 0.1}]
        with mock.patch.object(agent.rag, "retrieve", return_value=fake_ctx):
            out = agent.run_agent("high-protein paneer dinner under 100",
                                  llm=self._fake(True, [("recipe_recommender", {"goal": "high-protein", "diet": "veg", "max_cost_per_serving": 100})]))
        self.assertEqual(out["answer"], "final answer")
        self.assertEqual(out["tools_used"][0]["tool"], "recipe_recommender")
        self.assertTrue(out["tools_used"][0]["ok"])
        self.assertEqual(len(out["sources"]), 1)
        self.assertTrue(any(t.startswith("retrieve") for t in out["trace"]))

    def test_skips_rag_and_tools(self):
        from backend.ai import agent
        out = agent.run_agent("hello", llm=self._fake(False, []))
        self.assertEqual(out["tools_used"], [])
        self.assertFalse(any(t.startswith("retrieve") for t in out["trace"]))

    def test_tool_failure_is_reported(self):
        from backend.ai import agent
        out = agent.run_agent("x", llm=self._fake(False, [("nutrition_calculator", {"recipe": "Nope", "servings": 1})]))
        self.assertFalse(out["tools_used"][0]["ok"])
        self.assertTrue(out["problems"])

    def test_rag_unavailable_is_reported_not_hidden(self):
        from backend.ai import agent
        with mock.patch.object(agent.rag, "retrieve", side_effect=agent.rag.RagUnavailable("no store")):
            out = agent.run_agent("chicken safety", llm=self._fake(True, []))
        self.assertTrue(any("Knowledge base unavailable" in p for p in out["problems"]))


if __name__ == "__main__":
    unittest.main()
