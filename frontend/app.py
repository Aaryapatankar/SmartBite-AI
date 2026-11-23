"""Streamlit entry point. Run from the project root:  python -m streamlit run frontend/app.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from frontend import views  # noqa: E402

st.set_page_config(page_title="SmartBite AI", page_icon="🥗", layout="wide")
st.markdown(f"<style>{(ROOT / 'frontend' / 'styles.css').read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)

PAGES = {"Home": views.home, "Find Recipes": views.find_recipes, "Nutrition Analyzer": views.nutrition,
         "Budget Planner": views.budget, "Meal Planner": views.meal_planner,
         "AI Food Assistant": views.assistant, "About and Settings": views.about}
ICONS = {"Home": "🏠", "Find Recipes": "🔍", "Nutrition Analyzer": "🥗", "Budget Planner": "💰",
         "Meal Planner": "🗓️", "AI Food Assistant": "🤖", "About and Settings": "ℹ️"}

st.session_state.setdefault("page", "Home")
with st.sidebar:
    st.markdown('<div class="brand">🥗 SmartBite AI</div><div style="opacity:.8;margin-bottom:1rem">Eat smart, cook better</div>', unsafe_allow_html=True)
    choice = st.radio("Navigate", list(PAGES), index=list(PAGES).index(st.session_state.page),
                      format_func=lambda p: f"{ICONS[p]}  {p}", label_visibility="collapsed")
    st.session_state.page = choice
PAGES[st.session_state.page]()
