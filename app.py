import os
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

from agent.agent import build_agent_executor
from langchain_core.messages import HumanMessage, AIMessage

load_dotenv()

def extract_text(output) -> str:
    """Some models (e.g. Gemini) return output as a list of content blocks
    instead of a plain string. Pull out just the readable text."""
    if isinstance(output, str):
        return output
    if isinstance(output, list):
        parts = []
        for block in output:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts).strip()
    return str(output)

st.set_page_config(page_title="TravelGenie", page_icon="🧭", layout="centered")

hero_html = Path("static/hero.html").read_text()
components.html(hero_html, height=2400)

missing = [k for k in ["GOOGLE_API_KEY", "OPENWEATHERMAP_API_KEY", "TAVILY_API_KEY"] if not os.getenv(k)]
if missing:
    st.warning(f"Missing environment variables: {', '.join(missing)}. Add them to your .env file.")
    st.stop()

if "executor" not in st.session_state:
    st.session_state.executor = build_agent_executor()
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "display_history" not in st.session_state:
    st.session_state.display_history = []

st.markdown('<div id="chat-anchor"></div>', unsafe_allow_html=True)

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
            answer = extract_text(result["output"])
            st.markdown(answer)

    st.session_state.chat_history.append(HumanMessage(content=user_input))
    st.session_state.chat_history.append(AIMessage(content=answer))
    st.session_state.display_history.append(("assistant", answer))