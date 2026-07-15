import os
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

from agent.agent import build_agent_executor
from langchain_core.messages import HumanMessage, AIMessage

load_dotenv()

st.set_page_config(page_title="TravelGenie", page_icon="🧭", layout="centered")

hero_html = Path("static/hero.html").read_text()
components.html(hero_html, height=430)

st.markdown(
    "<h1 style='font-family:Georgia,serif;color:#1F1B16;'>TravelGenie</h1>"
    "<p style='color:#5c5647;'>Tell me where you're headed, your dates, and your budget — "
    "I'll chain weather, search, and booking tools into a day-by-day plan you can refine.</p>",
    unsafe_allow_html=True,
)

missing = [k for k in ["XAI_API_KEY", "OPENWEATHERMAP_API_KEY", "TAVILY_API_KEY"] if not os.getenv(k)]
if missing:
    st.warning(f"Missing environment variables: {', '.join(missing)}. Add them to your .env file.")
    st.stop()

if "executor" not in st.session_state:
    st.session_state.executor = build_agent_executor()
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "display_history" not in st.session_state:
    st.session_state.display_history = []

for role, text in st.session_state.display_history:
    with st.chat_message(role):
        st.markdown(text)

user_input = st.chat_input("e.g. Plan 5 days in Lisbon in October, budget $150/day")
if user_input:
    st.session_state.display_history.append(("user", user_input))
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        with st.spinner("Chaining tools: weather → search → booking → itinerary..."):
            result = st.session_state.executor.invoke({
                "input": user_input,
                "chat_history": st.session_state.chat_history,
            })
            answer = result["output"]
            st.markdown(answer)

    st.session_state.chat_history.append(HumanMessage(content=user_input))
    st.session_state.chat_history.append(AIMessage(content=answer))
    st.session_state.display_history.append(("assistant", answer))
