"""LangGraph agent.

Graph:  understand -> (retrieve?) -> plan_tools -> (execute_tools -> validate)? -> respond

 understand    : the LLM classifies the request and decides if the knowledge base (RAG) is needed.
 retrieve      : RAG retrieval from ChromaDB.
 plan_tools    : the LLM, with the 8 tools bound, chooses which tools to call (real tool calling).
 execute_tools : runs the chosen Python tools.
 validate      : checks every tool result and records problems.
 respond       : the LLM writes the final answer grounded in context + tool results.
"""
import json
import logging
import re
from typing import Any, TypedDict

from backend.ai import rag
from backend.ai.llm import get_llm, text_of
from backend.services import tools as T

log = logging.getLogger("smartbite.agent")


class AgentState(TypedDict, total=False):
    question: str
    needs_rag: bool
    context: list
    tool_calls: list
    tool_results: list
    problems: list
    answer: str
    trace: list


def make_lc_tools():
    """Wrap the Python tools as LangChain tools so the LLM can call them."""
    from langchain_core.tools import tool

    @tool("recipe_search")
    def recipe_search(query: str = "", diet: str = "any", meal: str = "any", max_time: int = 0, max_cost_per_serving: float = 0) -> dict:
        """Search recipes. diet: any/veg/non-veg. meal: any/breakfast/lunch/snack/dinner. Use 0 for no limit on max_time and max_cost_per_serving (INR)."""
        return T.recipe_search(query, diet, meal, max_time or None, max_cost_per_serving or None)

    @tool("ingredient_match")
    def ingredient_match(ingredients: list[str], diet: str = "any") -> dict:
        """Find recipes that can be made with the listed ingredients."""
        return T.ingredient_match(ingredients, diet)

    @tool("nutrition_calculator")
    def nutrition_calculator(recipe: str, servings: float = 1) -> dict:
        """Calories, protein, carbs and fat of a recipe (by name) for some servings."""
        return T.nutrition_calculator(recipe, servings)

    @tool("calorie_calculator")
    def calorie_calculator(ingredient_names: list[str], grams: list[float]) -> dict:
        """Calories and macros for custom ingredients. The two lists must be the same length."""
        if len(ingredient_names) != len(grams):
            return {"ok": False, "error": "ingredient_names and grams must have the same length"}
        return T.calorie_calculator([{"ingredient": n, "grams": g} for n, g in zip(ingredient_names, grams)])

    @tool("budget_estimator")
    def budget_estimator(recipe: str, servings: float = 0, budget: float = 0) -> dict:
        """Estimated cost in INR of a recipe (by name), compared with a budget. Use 0 for defaults."""
        return T.budget_estimator(recipe, servings or None, budget or None)

    @tool("meal_planner")
    def meal_planner(days: int = 1, diet: str = "any", budget_per_day: float = 0, daily_calorie_target: float = 0) -> dict:
        """Create a 1-7 day meal plan. Use 0 for no budget or calorie target."""
        return T.meal_planner(days, diet, budget_per_day or None, daily_calorie_target or None)

    @tool("food_substitution")
    def food_substitution(ingredient: str, diet: str = "any") -> dict:
        """Suggest substitutes for an ingredient."""
        return T.food_substitution(ingredient, diet)

    @tool("recipe_recommender")
    def recipe_recommender(goal: str = "balanced", diet: str = "any", meal: str = "any", max_cost_per_serving: float = 0, min_protein: float = 0) -> dict:
        """Recommend recipes. goal: high-protein/low-calorie/budget/balanced. Use 0 for no limit."""
        return T.recipe_recommender(goal, diet, meal, max_cost_per_serving or None, min_protein or None)

    return [recipe_search, ingredient_match, nutrition_calculator, calorie_calculator,
            budget_estimator, meal_planner, food_substitution, recipe_recommender]


def build_graph(llm=None):
    from langchain_core.messages import HumanMessage, SystemMessage
    from langgraph.graph import END, StateGraph

    llm = llm or get_llm()
    lc_tools = make_lc_tools()
    by_name = {t.name: t for t in lc_tools}
    tool_llm = llm.bind_tools(lc_tools)

    def understand(s: AgentState):
        msg = llm.invoke([SystemMessage(content=(
            "Classify the food question. Reply ONLY with JSON: {\"intent\": \"recipe|nutrition|budget|mealplan|substitution|safety|general\", "
            "\"needs_rag\": true or false}. needs_rag is true when the answer needs recipe, nutrition, cooking or food-safety knowledge.")),
            HumanMessage(content=s["question"])])
        raw = text_of(msg)
        try:
            parsed = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))
            needs = bool(parsed.get("needs_rag", True))
            intent = parsed.get("intent", "general")
        except Exception:
            needs, intent = True, "general"  # safe default: use the knowledge base
        return {"needs_rag": needs, "trace": s.get("trace", []) + [f"understand: intent={intent}, needs_rag={needs}"]}

    def retrieve(s: AgentState):
        problems = list(s.get("problems", []))
        try:
            ctx = rag.retrieve(s["question"], k=4)
        except rag.RagUnavailable as e:
            ctx = []
            problems.append(f"Knowledge base unavailable: {e}")
        return {"context": ctx, "problems": problems, "trace": s["trace"] + [f"retrieve: {len(ctx)} chunks"]}

    def plan_tools(s: AgentState):
        ctx = "\n".join(f"- {c['text'][:300]}" for c in s.get("context", []))
        msg = tool_llm.invoke([SystemMessage(content=(
            "You are SmartBite AI's planner. Call the tools needed to answer the user's food question with real numbers "
            "(costs are in INR). If no tool is needed, do not call any. Known context:\n" + ctx)),
            HumanMessage(content=s["question"])])
        calls = [{"name": c["name"], "args": c.get("args", {})} for c in (getattr(msg, "tool_calls", None) or [])]
        return {"tool_calls": calls, "trace": s["trace"] + [f"plan_tools: {[c['name'] for c in calls] or 'no tools'}"]}

    def execute_tools(s: AgentState):
        results = []
        for c in s["tool_calls"]:
            try:
                res = by_name[c["name"]].invoke(c["args"]) if c["name"] in by_name else {"ok": False, "error": f"unknown tool {c['name']}"}
            except Exception as e:
                res = {"ok": False, "error": f"tool crashed: {e}"}
            results.append({"tool": c["name"], "args": c["args"], "result": res})
        return {"tool_results": results, "trace": s["trace"] + [f"execute_tools: ran {len(results)}"]}

    def validate(s: AgentState):
        problems = list(s.get("problems", []))
        for r in s["tool_results"]:
            if not isinstance(r["result"], dict) or not r["result"].get("ok"):
                problems.append(f"Tool {r['tool']} failed: {r['result'].get('error') if isinstance(r['result'], dict) else r['result']}")
        return {"problems": problems, "trace": s["trace"] + [f"validate: {len(problems)} problem(s)"]}

    def respond(s: AgentState):
        ctx = "\n".join(f"[S{i + 1}] ({c['source']}) {c['text']}" for i, c in enumerate(s.get("context", []))) or "(no knowledge-base context)"
        tr = json.dumps(s.get("tool_results", []), default=str)[:6000] or "[]"
        msg = llm.invoke([SystemMessage(content=(
            "You are SmartBite AI, a friendly Indian food and nutrition assistant. Rules: use ONLY the knowledge-base context and tool results "
            "for facts and numbers; cite knowledge sources like [S1]; say clearly when information is not available instead of guessing; "
            "label nutrition and cost as estimates; mention tool failures honestly; suggestions you invent yourself must be marked as AI suggestions; "
            "no medical advice. Be concise.")),
            HumanMessage(content=f"Question: {s['question']}\n\nKnowledge context:\n{ctx}\n\nTool results:\n{tr}\n\nProblems: {s.get('problems', [])}")])
        return {"answer": text_of(msg), "trace": s["trace"] + ["respond: answer generated"]}

    g = StateGraph(AgentState)
    for name, fn in (("understand", understand), ("retrieve", retrieve), ("plan_tools", plan_tools),
                     ("execute_tools", execute_tools), ("validate", validate), ("respond", respond)):
        g.add_node(name, fn)
    g.set_entry_point("understand")
    g.add_conditional_edges("understand", lambda s: "retrieve" if s.get("needs_rag") else "plan_tools")
    g.add_edge("retrieve", "plan_tools")
    g.add_conditional_edges("plan_tools", lambda s: "execute_tools" if s.get("tool_calls") else "respond")
    g.add_edge("execute_tools", "validate")
    g.add_edge("validate", "respond")
    g.add_edge("respond", END)
    return g.compile()


def run_agent(question: str, llm=None) -> dict:
    final = build_graph(llm).invoke({"question": question, "trace": [], "problems": []})
    return {"answer": final.get("answer", ""),
            "sources": [{"source": c["source"], "text": c["text"][:300]} for c in final.get("context", [])],
            "tools_used": [{"tool": r["tool"], "args": r["args"], "ok": bool(r["result"].get("ok")) if isinstance(r["result"], dict) else False,
                            "result": r["result"]} for r in final.get("tool_results", [])],
            "trace": final.get("trace", []), "problems": final.get("problems", [])}
