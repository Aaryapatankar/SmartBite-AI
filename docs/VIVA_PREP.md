# Viva preparation
1. **What is Generative AI here?** Gemini (or Ollama) writes custom recipes, routes questions, chooses tools and writes final answers.
2. **What is RAG and where is it?** `backend/ai/rag.py`: documents -> chunks -> embeddings -> ChromaDB -> top-4 retrieval -> context in the prompt. Answers cite [S1], [S2].
3. **Why RAG?** To ground answers in our documents and reduce hallucination; if nothing relevant is retrieved the model must say it does not know.
4. **What is tool calling?** The LLM receives tool schemas and returns structured calls (`recipe_search`, ...). Our code executes them and returns results to the LLM. See `agent.py` `plan_tools` and `execute_tools`.
5. **Why LangGraph?** Explicit nodes and conditional edges make the workflow visible and explainable.
6. **How is nutrition calculated?** Sum(grams/100 x per-100g value) over ingredients, divided by servings. Values are approximate, so results are estimates.
7. **How do you avoid fake data?** Labels on every value, honest README, tool errors reported, no hardcoded AI answers.
8. **Chunking choices?** 600 characters with 80 overlap keeps a fact together while allowing context continuity.
9. **What if the API key is missing?** The API returns 503 with instructions; non-AI pages still work.
10. **Validation?** Pydantic at the API plus manual checks in each tool (diet, positive numbers, unknown recipes/ingredients).
11. **Limitations?** Small dataset, approximate values, unpinned dependencies, launcher and AI parts need testing on your machine.
12. **Demo script:** Home -> Find Recipes (paneer, spinach) -> Nutrition -> Budget -> Weekly plan -> Assistant: "Suggest a high-protein Indian dinner using paneer under ₹100" -> open Tools, Sources, Workflow expanders.
