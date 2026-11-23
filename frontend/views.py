"""All Streamlit pages. Each function draws one page."""
import pandas as pd
import streamlit as st

from frontend.api import call

EMOJI = {"breakfast": "🥣", "lunch": "🍛", "dinner": "🍲", "snack": "🥗"}


def error(msg):
    st.markdown(f'<div class="err">⚠️ {msg}</div>', unsafe_allow_html=True)


def go(page):
    st.session_state.page = page
    st.rerun()


@st.cache_data(ttl=60, show_spinner=False)
def recipe_names():
    ok, data = call("GET", "/api/recipes")
    return {r["name"]: r["id"] for r in data} if ok else {}


def card(emoji, title, text):
    st.markdown(f'<div class="card"><div class="emoji">{emoji}</div><h4>{title}</h4><p>{text}</p></div>', unsafe_allow_html=True)


def recipe_card(r, key):
    pill = "veg" if r["diet"] == "veg" else "nonveg"
    icon = EMOJI.get(r["meals"][0], "🍽️")
    st.markdown(f'''<div class="card"><div class="recipe-img">{icon}</div><h4>{r["name"]}</h4>
      <span class="pill {pill}">{"Veg" if r["diet"] == "veg" else "Non-veg"}</span><span class="pill info">⏱ {r["time_min"]} min</span>
      <span class="pill info">₹{r["cost_per_serving"]}/serving</span>
      <p style="margin-top:.5rem">{r["calories"]} kcal · {r["protein"]} g protein per serving<br>
      <span class="label">calculated estimate</span></p></div>''', unsafe_allow_html=True)
    with st.expander("Ingredients and steps"):
        ok, full = call("GET", f"/api/recipes/{r['id']}")
        if ok:
            st.markdown(f"**Makes {full['servings']} servings**")
            st.table(pd.DataFrame(full["ingredients"], columns=["Ingredient", "Grams"]))
            for i, s in enumerate(full["steps"], 1):
                st.markdown(f"{i}. {s}")
        if st.button("💾 Save recipe", key=f"save{key}{r['id']}"):
            ok, _ = call("POST", f"/api/saved/{r['id']}")
            st.success("Saved!") if ok else error("Could not save")


def show_cards(items, prefix):
    cols = st.columns(3)
    for i, r in enumerate(items):
        with cols[i % 3]:
            recipe_card(r, prefix)


def home():
    st.markdown('<div class="hero"><h1>Cook smart. Eat well. 🌿</h1><p>SmartBite AI helps you find Indian recipes from what you have, '
                'understand nutrition, plan meals and stay on budget, powered by Generative AI, RAG and tool calling.</p></div>', unsafe_allow_html=True)
    st.subheader("Quick actions")
    cols = st.columns(4)
    acts = [("🔍", "Find Recipes", "Cook with what you have"), ("🥗", "Nutrition Analyzer", "Calories and macros"),
            ("💰", "Budget Planner", "Cost per serving"), ("🤖", "AI Food Assistant", "Ask anything about food")]
    for col, (e, t, d) in zip(cols, acts):
        with col:
            card(e, t, d)
            if st.button("Open", key="qa" + t):
                go(t)
    st.subheader("Featured: high-protein picks")
    ok, d = call("POST", "/api/recommend", {"goal": "high-protein", "top_n": 3})
    show_cards(d["data"]["recommendations"], "home") if ok else error(d)


def find_recipes():
    st.title("🔍 Find Recipes")
    ok, names = call("GET", "/api/ingredients")
    c1, c2 = st.columns(2)
    chosen = c1.multiselect("Ingredients you have", names if ok else [], placeholder="Pick ingredients")
    extra = c1.text_input("Other ingredients (comma separated)")
    diet = c2.radio("Diet", ["any", "veg", "non-veg"], horizontal=True)
    meal = c2.selectbox("Meal", ["any", "breakfast", "lunch", "snack", "dinner"])
    max_time = c2.slider("Max cooking time (min)", 10, 90, 60, 5)
    budget = c2.number_input("Max cost per serving (₹, 0 = no limit)", 0, 1000, 0)
    cuisine = c1.selectbox("Cuisine", ["Indian (more cuisines can be added later)"])
    if st.button("Find recipes"):
        ings = chosen + [x.strip() for x in extra.split(",") if x.strip()]
        if ings:
            ok, d = call("POST", "/api/recipes/match", {"ingredients": ings, "diet": diet})
            if not ok:
                return error(d)
            if d["data"]["unrecognized"]:
                st.info(f"Not in dataset: {', '.join(d['data']['unrecognized'])}")
            items = [m for m in d["data"]["matches"] if m["time_min"] <= max_time and (not budget or m["cost_per_serving"] <= budget)]
            for m in items:
                m["match"] = f"{m['match_pct']}% match, missing: {', '.join(m['missing']) or 'nothing'}"
        else:
            ok, d = call("POST", "/api/recipes/search", {"diet": diet, "meal": meal, "max_time": max_time,
                                                         "max_cost_per_serving": budget or None})
            if not ok:
                return error(d)
            items = d["data"]
        if not items:
            st.warning("No recipes match these filters. Try relaxing them.")
        for m in items:
            if m.get("match"):
                st.caption(f"**{m['name']}**: {m['match']}")
        show_cards(items, "find")
    with st.expander("✨ Generate a custom recipe with AI"):
        notes = st.text_input("Extra wishes (optional)")
        if st.button("Generate with AI"):
            ings = chosen + [x.strip() for x in extra.split(",") if x.strip()]
            if not ings:
                return error("Pick at least one ingredient first.")
            with st.spinner("Asking the AI..."):
                ok, d = call("POST", "/api/ai/generate-recipe", {"ingredients": ings, "diet": "veg" if diet == "any" else diet,
                                                                  "max_time": max_time, "notes": notes})
            if ok:
                st.markdown(d["recipe"])
                st.markdown(f'<span class="label">{d["label"]}</span>', unsafe_allow_html=True)
            else:
                error(d)


def nutrition():
    st.title("🥗 Nutrition Analyzer")
    names = recipe_names()
    if not names:
        return error("Could not load recipes. Is the backend running?")
    c1, c2 = st.columns(2)
    name = c1.selectbox("Recipe", list(names))
    servings = c2.number_input("Servings", 0.5, 50.0, 1.0, 0.5)
    if st.button("Analyze"):
        ok, d = call("POST", "/api/nutrition", {"recipe": name, "servings": servings})
        if not ok:
            return error(d)
        t = d["data"]["total"]
        m = st.columns(4)
        m[0].metric("Calories", f"{t['calories']} kcal"); m[1].metric("Protein", f"{t['protein']} g")
        m[2].metric("Carbs", f"{t['carbs']} g"); m[3].metric("Fat", f"{t['fat']} g")
        st.caption("Calculated estimate from approximate ingredient values, not lab verified.")
        st.bar_chart(pd.DataFrame({"grams": [t["protein"], t["carbs"], t["fat"]]}, index=["Protein", "Carbs", "Fat"]))
        st.subheader("Ingredient-wise breakdown")
        st.dataframe(pd.DataFrame(d["data"]["breakdown"]).rename(columns={"kcal": "calories"}), hide_index=True, use_container_width=True)
    with st.expander("Custom calorie calculator"):
        txt = st.text_area("One per line: ingredient, grams", "paneer, 100\nrice, 150")
        if st.button("Calculate calories"):
            items = []
            for line in txt.splitlines():
                if line.strip():
                    p = [x.strip() for x in line.split(",")]
                    try:
                        items.append({"ingredient": p[0], "grams": float(p[1])})
                    except (IndexError, ValueError):
                        return error(f"Cannot read line: '{line}'. Use: ingredient, grams")
            ok, d = call("POST", "/api/calories", {"items": items})
            st.json(d["data"]["total"]) if ok else error(d)


def budget():
    st.title("💰 Budget Planner")
    names = recipe_names()
    if not names:
        return error("Could not load recipes. Is the backend running?")
    c1, c2, c3 = st.columns(3)
    name = c1.selectbox("Recipe", list(names))
    servings = c2.number_input("Servings", 1, 50, 2)
    bud = c3.number_input("Your budget (₹)", 1, 100000, 100)
    if st.button("Estimate cost"):
        ok, d = call("POST", "/api/budget", {"recipe": name, "servings": servings, "budget": bud})
        if not ok:
            return error(d)
        x = d["data"]
        m = st.columns(3)
        m[0].metric("Total cost", f"₹{x['total_cost']}"); m[1].metric("Per serving", f"₹{x['cost_per_serving']}")
        m[2].metric("vs budget", f"₹{abs(x['difference'])} {'under' if x['within_budget'] else 'over'}")
        st.success("Within budget ✅") if x["within_budget"] else st.warning("Over budget")
        st.caption("Prices are approximate Indian retail averages and vary by city and season.")
        st.bar_chart(pd.DataFrame(x["breakdown"]).set_index("ingredient")["cost"])
        if x["cheaper_alternatives"]:
            st.subheader("Cheaper alternatives")
            show_cards(x["cheaper_alternatives"], "alt")


def meal_planner():
    st.title("🗓️ Meal Planner")
    c1, c2, c3 = st.columns(3)
    mode = c1.radio("Plan", ["Daily", "Weekly"], horizontal=True)
    diet = c2.selectbox("Diet", ["any", "veg", "non-veg"])
    bud = c3.number_input("Budget per day (₹, 0 = none)", 0, 5000, 0)
    cal = st.number_input("Daily calorie target (0 = none)", 0, 5000, 0)
    if st.button("Generate plan"):
        ok, d = call("POST", "/api/mealplan", {"days": 1 if mode == "Daily" else 7, "diet": diet,
                                               "budget_per_day": bud or None, "daily_calorie_target": cal or None})
        if not ok:
            return error(d)
        st.session_state.plan = d["data"]
    plan = st.session_state.get("plan")
    if plan:
        for n in plan["notes"]:
            st.info(n)
        tabs = st.tabs([f"Day {x['day']}" for x in plan["days"]])
        for tab, day in zip(tabs, plan["days"]):
            with tab:
                for meal, r in day["meals"].items():
                    st.markdown(f"**{EMOJI[meal]} {meal.title()}**: {r['name']} · {r['calories']} kcal · {r['protein']} g protein · ₹{r['cost_per_serving']}")
                t = day["totals"]
                m = st.columns(5)
                m[0].metric("Calories", t["calories"]); m[1].metric("Protein", f"{t['protein']} g"); m[2].metric("Carbs", f"{t['carbs']} g")
                m[3].metric("Fat", f"{t['fat']} g"); m[4].metric("Cost", f"₹{day['cost']}")
                if day["within_budget"] is False:
                    st.warning("Over budget")
        if st.button("💾 Save this plan"):
            ok, _ = call("POST", "/api/mealplan/save", plan, params={"title": f"{mode} plan"})
            st.success("Plan saved") if ok else error("Could not save")


def assistant():
    st.title("🤖 AI Food Assistant")
    st.caption("Answers use the knowledge base (RAG) and calculator tools. If the AI key is missing you will see a clear message.")
    msgs = st.session_state.setdefault("msgs", [])
    for m in msgs:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
            if m.get("meta"):
                meta_view(m["meta"])
    q = st.chat_input("e.g. Suggest a high-protein Indian dinner using paneer under ₹100")
    if q:
        msgs.append({"role": "user", "content": q})
        with st.chat_message("user"):
            st.markdown(q)
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                ok, d = call("POST", "/api/chat", {"question": q}, timeout=180)
            if ok:
                st.markdown(d["answer"]); meta_view(d)
                msgs.append({"role": "assistant", "content": d["answer"], "meta": d})
            else:
                error(d)


def meta_view(d):
    if d["tools_used"]:
        with st.expander(f"🛠️ Tools executed ({len(d['tools_used'])})"):
            for t in d["tools_used"]:
                st.markdown(f"**{t['tool']}** {'✅' if t['ok'] else '❌'}"); st.json(t["args"])
    if d["sources"]:
        with st.expander(f"📚 Sources retrieved ({len(d['sources'])})"):
            for i, s in enumerate(d["sources"], 1):
                st.markdown(f"**[S{i}] {s['source']}**: {s['text']}...")
    with st.expander("🧭 Agent workflow"):
        for step in d["trace"]:
            st.markdown(f"- {step}")
        for p in d["problems"]:
            st.warning(p)


def about():
    st.title("ℹ️ About and Settings")
    st.markdown("""**SmartBite AI** is an Indian recipe and nutrition assistant built for a Generative AI course project.

**Technologies:** Python, FastAPI, Pydantic, Streamlit, LangChain, LangGraph, ChromaDB, SQLite, Gemini (or Ollama).

**AI architecture:** the LangGraph agent understands the question, optionally retrieves knowledge (RAG), lets the LLM pick tools (tool calling),
validates tool results and writes a grounded answer. Values are labelled *dataset*, *calculated estimate* or *AI suggestion*.""")
    st.subheader("Dietary preferences")
    ok, prefs = call("GET", "/api/preferences")
    diet = st.selectbox("Default diet", ["any", "veg", "non-veg"], index=["any", "veg", "non-veg"].index(prefs.get("diet", "any")) if ok else 0)
    if st.button("Save preferences"):
        ok, _ = call("POST", "/api/preferences", {"diet": diet})
        st.success("Saved") if ok else error("Could not save")
    st.subheader("System status")
    ok, h = call("GET", "/api/health")
    st.success(f"Backend OK ({h['recipes']} recipes)") if ok else error(h)
    ok, r = call("GET", "/api/rag/status", timeout=300)
    if ok and r.get("available"):
        st.success(f"Knowledge base ready ({r['chunks']} chunks)")
    elif ok:
        st.warning(f"Knowledge base not ready: {r.get('error')}")
    if st.button("Rebuild knowledge base"):
        with st.spinner("Indexing (first run downloads the embedding model)..."):
            ok, r = call("POST", "/api/rag/rebuild", timeout=600)
        st.success(f"Done: {r['chunks']} chunks") if ok else error(r)
