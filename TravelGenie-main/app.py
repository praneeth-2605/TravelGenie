import os
import re
from pathlib import Path
import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

from agent.agent import build_agent_executor
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.callbacks import BaseCallbackHandler
import time

# Load environment variables
load_dotenv()

# Streamlit App Configurations
st.set_page_config(page_title="TravelGenie", page_icon="🧭", layout="wide")

# Theme styling variables
PRIMARY_COLOR = "#D97757"
BACKGROUND_COLOR = "#F4F1EA"
SECONDARY_BACKGROUND_COLOR = "#EAE5DB"
TEXT_COLOR = "#1F1B16"

# Inject Custom CSS for premium styling
st.markdown(
    f"""
    <style>
    /* Main app background */
    .stApp {{
        background-color: {BACKGROUND_COLOR};
        color: {TEXT_COLOR};
    }}
    /* Title font family styling */
    h1, h2, h3, .custom-title {{
        font-family: Georgia, serif !important;
        color: {TEXT_COLOR};
    }}
    /* Styled widgets & custom layout tags */
    .metric-container {{
        background-color: {SECONDARY_BACKGROUND_COLOR};
        border-radius: 8px;
        padding: 12px 20px;
        text-align: center;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }}
    .badge {{
        background-color: {PRIMARY_COLOR};
        color: white;
        padding: 4px 10px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 500;
        margin-right: 5px;
        display: inline-block;
    }}
    </style>
    """,
    unsafe_allow_html=True
)

# Helper: Retrieve Destination Coordinates using OpenWeatherMap API
def get_coordinates(city: str) -> tuple[float, float] | None:
    api_key = os.getenv("OPENWEATHERMAP_API_KEY")
    if not api_key:
        return None
    try:
        geo = requests.get(
            "https://api.openweathermap.org/geo/1.0/direct",
            params={"q": city, "limit": 1, "appid": api_key},
            timeout=5,
        ).json()
        if geo:
            return float(geo[0]["lat"]), float(geo[0]["lon"])
    except Exception:
        pass
    return None

# Helper: Parse response sections based on structured headers
def parse_sections(text: str) -> dict:
    sections = {
        "itinerary": "",
        "hotels": "",
        "restaurants": "",
        "budget": "",
        "weather": ""
    }
    
    headers = [
        (r"##\s*ITINERARY", "itinerary"),
        (r"##\s*HOTEL\s*SUGGESTIONS", "hotels"),
        (r"##\s*RESTAURANT\s*RECOMMENDATIONS", "restaurants"),
        (r"##\s*BUDGET\s*BREAKDOWN", "budget"),
        (r"##\s*WEATHER\s*&\s*PACKING", "weather")
    ]
    
    matches = []
    for pattern, key in headers:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            matches.append((match.start(), match.end(), key))
            
    matches.sort(key=lambda x: x[0])
    
    if not matches:
        sections["itinerary"] = text
        return sections
        
    for i in range(len(matches)):
        start_idx = matches[i][1]
        end_idx = matches[i+1][0] if i + 1 < len(matches) else len(text)
        content = text[start_idx:end_idx].strip()
        sections[matches[i][2]] = content
        
    return sections

# Helper: Render Mock Bookings as Visual HTML Cards
def format_mock_bookings(text: str) -> str:
    # Pattern: [MOCK BOOKING] details — confirmation code, est. price
    pattern = r"\[MOCK BOOKING\]\s+([^—\n]+)—\s*confirmation\s+([\w-]+)(?:,\s*est\.\s*([^.\n]+))?\.?"
    
    replacement = f"""
    <div style="background-color: {SECONDARY_BACKGROUND_COLOR}; border-left: 5px solid {PRIMARY_COLOR}; padding: 12px; border-radius: 6px; margin: 10px 0; font-family: sans-serif;">
        <div style="font-size: 10px; font-weight: bold; color: #8A6F5C; letter-spacing: 0.08em; text-transform: uppercase;">🎫 Booking Confirmation</div>
        <div style="font-size: 14px; font-weight: bold; color: {TEXT_COLOR}; margin: 5px 0;">{{0}}</div>
        <div style="display: flex; gap: 15px; font-size: 12px; color: #5c5647;">
            <span>🔑 <b>Code:</b> <code>{{1}}</code></span>
            {{2}}
        </div>
    </div>
    """
    
    def repl(match):
        details = match.group(1).strip()
        code = match.group(2).strip()
        price = match.group(3)
        price_str = f"<span>💰 <b>Est:</b> {price.strip()}</span>" if price else ""
        return replacement.format(details, code, price_str)
        
    return re.sub(pattern, repl, text)

# Helper: Parse Day-by-Day Itinerary into Tabs
def parse_itinerary_days(itinerary_text: str) -> list[tuple[str, str]]:
    # Match headers like "### Day 1", "Day 1:", "## Day 1"
    pattern = r"(?:^|\n)(?=###?\s*Day\s*\d+)"
    parts = re.split(pattern, itinerary_text)
    
    days_list = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        lines = part.split("\n")
        header = lines[0].replace("###", "").replace("##", "").strip()
        content = "\n".join(lines[1:]).strip()
        days_list.append((header, content))
    return days_list

# Helper: Extract String Text from Google GenAI Content Block Lists
def extract_text_output(output) -> str:
    if isinstance(output, str):
        return output
    elif isinstance(output, list):
        parts = []
        for block in output:
            if isinstance(block, dict) and "text" in block:
                parts.append(block["text"])
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return str(output)

# Helper: Callbacks Handler to display progress bars dynamically
class ProgressCallbackHandler(BaseCallbackHandler):
    def __init__(self, placeholder):
        self.placeholder = placeholder
        self.progress = {
            "Planner Agent": 30,
            "Flight Agent": 10,
            "Hotel Agent": 10,
            "Weather Agent": 10,
            "Restaurant Agent": 10,
            "Maps Agent": 10
        }
        self.last_agent = None
        self.update_display()
        
    def update_display(self):
        emojis = {
            "Planner Agent": "🧠",
            "Flight Agent": "✈",
            "Hotel Agent": "🏨",
            "Weather Agent": "🌦",
            "Restaurant Agent": "🍽",
            "Maps Agent": "📍"
        }
        
        items_html = ""
        for agent, val in self.progress.items():
            emoji = emojis.get(agent, "🤖")
            items_html += f"""
            <div style="margin-bottom: 18px; font-family: sans-serif;">
                <div style="display: flex; justify-content: space-between; font-size: 14px; font-weight: 600; color: #1F1B16; margin-bottom: 6px;">
                    <span>{emoji} {agent}</span>
                    <span style="color: #D97757; font-weight: bold;">{val}%</span>
                </div>
                <div style="background-color: #D3C9B8; border-radius: 10px; height: 10px; overflow: hidden; width: 100%;">
                    <div style="background: linear-gradient(90deg, #D97757 0%, #E09176 100%); height: 100%; width: {val}%; border-radius: 10px; transition: width 0.3s ease-in-out;"></div>
                </div>
            </div>
            """
            
        container_html = f"""
        <div style="background-color: #EAE5DB; border-radius: 14px; padding: 25px; box-shadow: 0 4px 20px rgba(0,0,0,0.06); max-width: 500px; margin: 20px auto; border: 1px solid #D3C9B8;">
            <h3 style="margin-top: 0; color: #1F1B16; font-family: Georgia, serif; text-align: center; font-size: 22px; margin-bottom: 25px; border-bottom: 2px solid #D3C9B8; padding-bottom: 12px; font-weight: bold;">🧭 Travel Planning Progress</h3>
            {items_html}
        </div>
        """
        self.placeholder.html(container_html)
        
    def animate_to(self, agent, target_val, steps=8, delay=0.02):
        start_val = self.progress.get(agent, 0)
        if start_val == target_val:
            return
        for i in range(1, steps + 1):
            current_val = int(start_val + (target_val - start_val) * (i / steps))
            self.progress[agent] = current_val
            # Slowly pull planner agent up as other agents make progress
            if agent != "Planner Agent" and self.progress["Planner Agent"] < 90:
                self.progress["Planner Agent"] = min(90, self.progress["Planner Agent"] + 1)
            self.update_display()
            time.sleep(delay)
            
    def on_tool_start(self, serialized, input_str, **kwargs):
        tool_name = serialized.get("name", "")
        if "weather" in tool_name.lower():
            self.last_agent = "Weather Agent"
            self.animate_to("Weather Agent", 60)
            self.animate_to("Planner Agent", 60)
        elif "search" in tool_name.lower():
            self.last_agent = "Flight Agent"
            self.animate_to("Flight Agent", 60)
            self.animate_to("Restaurant Agent", 60)
            self.animate_to("Planner Agent", 50)
        elif "book" in tool_name.lower():
            self.last_agent = "Hotel Agent"
            self.animate_to("Hotel Agent", 60)
            self.animate_to("Planner Agent", 80)

    def on_tool_end(self, output, **kwargs):
        if self.last_agent:
            self.animate_to(self.last_agent, 100)
            if self.last_agent == "Flight Agent":
                self.animate_to("Restaurant Agent", 100)
            self.last_agent = None

# Verify credentials before loading agent
missing = [k for k in ["GOOGLE_API_KEY", "OPENWEATHERMAP_API_KEY", "TAVILY_API_KEY"] if not os.getenv(k)]
if missing:
    st.warning(f"Missing environment variables: {', '.join(missing)}. Add them to your .env file.")
    st.stop()

# Initialize session state variables
if "page" not in st.session_state:
    st.session_state.page = "landing"
if "executor" not in st.session_state:
    st.session_state.executor = build_agent_executor()
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "display_history" not in st.session_state:
    st.session_state.display_history = []
if "destination" not in st.session_state:
    st.session_state.destination = ""
if "start_date" not in st.session_state:
    st.session_state.start_date = None
if "end_date" not in st.session_state:
    st.session_state.end_date = None
if "budget" not in st.session_state:
    st.session_state.budget = 150
if "interests" not in st.session_state:
    st.session_state.interests = []
if "raw_response" not in st.session_state:
    st.session_state.raw_response = ""
if "sections" not in st.session_state:
    st.session_state.sections = {}
if "coords" not in st.session_state:
    st.session_state.coords = None

# ==============================================================================
# SCREEN 1: LANDING & PREFERENCES PAGE
# ==============================================================================
if st.session_state.page == "landing":
    hero_html_path = Path("static/hero.html")
    if hero_html_path.exists():
        st.iframe(hero_html_path, height=360)

    # Centering columns for landing layout
    col_margin_left, col_center, col_margin_right = st.columns([1, 4, 1])

    with col_center:
        st.markdown(
            f"<h1 style='text-align: center; color: {TEXT_COLOR}; font-family: Georgia, serif;'>TravelGenie 🧭</h1>"
            "<p style='text-align: center; color: #5c5647; font-size: 16px; margin-bottom: 30px;'>"
            "A smart assistant that integrates weather forecasts, live web searches, and mock booking cards "
            "into a day-by-day interactive travel dashboard.</p>",
            unsafe_allow_html=True
        )

        with st.form("preferences_form"):
            st.markdown("### 🌴 Plan Your Next Adventure")
            
            # Destination Search
            destination = st.text_input("Where are you heading?", placeholder="e.g. Lisbon, Portugal", value=st.session_state.destination)
            
            # Sub-columns for Dates and Budget
            col_left, col_right = st.columns(2)
            with col_left:
                dates = st.date_input("Trip Dates", value=())
            with col_right:
                budget = st.number_input("Budget per Day (USD)", min_value=10, max_value=10000, value=st.session_state.budget, step=25)
                
            # Interests Selection
            interests = st.multiselect(
                "What are your travel interests?",
                ["Culture & History", "Gastronomy & Food", "Nature & Outdoors", "Adventure & Sports", "Shopping", "Relaxation & Wellness", "Nightlife"],
                default=["Culture & History", "Gastronomy & Food"]
            )
            
            submit_btn = st.form_submit_button("✨ Generate Dashboard & Itinerary")
            
            if submit_btn:
                if not destination:
                    st.error("Please enter a destination to start planning.")
                elif not isinstance(dates, (tuple, list)) or len(dates) < 2:
                    st.error("Please select a range containing both a Start Date and End Date.")
                else:
                    st.session_state.destination = destination
                    st.session_state.start_date = dates[0]
                    st.session_state.end_date = dates[1]
                    st.session_state.budget = budget
                    st.session_state.interests = interests
                    st.session_state.page = "executing"
                    st.rerun()

# ==============================================================================
# SCREEN 2: AGENT EXECUTION LOADER
# ==============================================================================
elif st.session_state.page == "executing":
    col_margin_left, col_center, col_margin_right = st.columns([1, 3, 1])
    
    with col_center:
        st.markdown(
            f"<h2 style='text-align: center; color: {TEXT_COLOR}; font-family: Georgia, serif; margin-top: 30px;'>Crafting Your Journey...</h2>",
            unsafe_allow_html=True
        )
        
        # Container for the live progress dashboard
        progress_container = st.empty()
        handler = ProgressCallbackHandler(progress_container)
        
        # Step 1: Geolocation Coordinates
        coords = get_coordinates(st.session_state.destination)
        if coords:
            st.session_state.coords = coords
            handler.progress["Maps Agent"] = 100
            handler.progress["Planner Agent"] = 40
            handler.update_display()
        else:
            handler.progress["Maps Agent"] = 100
            handler.update_display()

        # Step 2: Build Query & Run Agent Executor
        duration = (st.session_state.end_date - st.session_state.start_date).days + 1
        
        query = f"Plan a trip to {st.session_state.destination}."
        query += f" Dates: from {st.session_state.start_date} to {st.session_state.end_date} ({duration} days)."
        query += f" Budget: ${st.session_state.budget}/day."
        if st.session_state.interests:
            query += f" Interests: {', '.join(st.session_state.interests)}."

        # Execute Langchain Agent Workflow with Callbacks
        try:
            result = st.session_state.executor.invoke({
                "input": query,
                "chat_history": []
            }, config={"callbacks": [handler]})
            output_text = extract_text_output(result["output"])
            
            # Step 3: Parse Sections
            st.session_state.raw_response = output_text
            st.session_state.sections = parse_sections(output_text)
            
            # Initialize conversational history for refinement chat
            st.session_state.chat_history = [
                HumanMessage(content=query),
                AIMessage(content=output_text)
            ]
            st.session_state.display_history = [
                ("user", query),
                ("assistant", output_text)
            ]
            
            # Finalize progress bar dashboard with smooth scroll to 100
            for k in handler.progress:
                handler.animate_to(k, 100, steps=8, delay=0.01)
            time.sleep(0.5) # Allow user to see completed state briefly
            
            st.session_state.page = "dashboard"
            st.rerun()
            
        except Exception as e:
            st.error(f"The Gemini AI model is currently unavailable or experiencing high demand: {e}. Please wait a moment and try again.")
            if st.button("⬅️ Back to Search"):
                st.session_state.page = "landing"
                st.rerun()
            st.stop()

# ==============================================================================
# SCREEN 3: DASHBOARD VIEW
# ==============================================================================
elif st.session_state.page == "dashboard":
    # --------------------------------------------------------------------------
    # SIDEBAR: NAVIGATION, PREFERENCES SUMMARY & EXPORT OPTIONS
    # --------------------------------------------------------------------------
    with st.sidebar:
        st.markdown(
            f"<h2 style='color: {TEXT_COLOR}; font-family: Georgia, serif;'>Navigation & Options</h2>",
            unsafe_allow_html=True
        )
        
        # Summary Card
        st.markdown(
            f"""
            <div style="background-color: {SECONDARY_BACKGROUND_COLOR}; padding: 15px; border-radius: 8px; margin-bottom: 20px;">
                <h4 style="margin: 0; color: {TEXT_COLOR}; font-family: Georgia, serif;">📍 {st.session_state.destination}</h4>
                <p style="font-size: 13px; color: #5c5647; margin: 5px 0;">
                    📅 {st.session_state.start_date} to {st.session_state.end_date}<br>
                    💰 Budget: ${st.session_state.budget}/day
                </p>
                <div style="margin-top: 8px;">
                    {" ".join([f"<span class='badge'>{interest}</span>" for interest in st.session_state.interests])}
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
        
        # Save, Export & Reset triggers
        st.markdown("### Actions")
        
        # Reset Page state
        if st.button("🔄 Plan Another Trip", width="stretch"):
            st.session_state.page = "landing"
            st.session_state.chat_history = []
            st.session_state.display_history = []
            st.session_state.destination = ""
            st.session_state.coords = None
            st.session_state.raw_response = ""
            st.session_state.sections = {}
            st.rerun()
            
        # Export content compiles
        export_text = f"""# Trip Itinerary to {st.session_state.destination}
Dates: {st.session_state.start_date} to {st.session_state.end_date}
Budget: ${st.session_state.budget}/day
Interests: {", ".join(st.session_state.interests)}

{st.session_state.raw_response}
"""
        st.download_button(
            label="📥 Download Itinerary (MD)",
            data=export_text,
            file_name=f"itinerary_{st.session_state.destination.lower().replace(' ', '_')}.md",
            mime="text/markdown",
            width="stretch"
        )
        
        st.info("💡 You can refine this itinerary using the AI Assistant chat tab on the right side of the dashboard.")

    # --------------------------------------------------------------------------
    # MAIN AREA: DASHBOARD METRICS & COLUMNS LAYOUT
    # --------------------------------------------------------------------------
    st.markdown(
        f"<h1 style='color: {TEXT_COLOR}; font-family: Georgia, serif;'>🗺️ Travel Dashboard: {st.session_state.destination}</h1>",
        unsafe_allow_html=True
    )
    
    # Grid of Metric Cards
    m_col1, m_col2, m_col3 = st.columns(3)
    duration_days = (st.session_state.end_date - st.session_state.start_date).days + 1
    with m_col1:
        st.markdown(
            f"""
            <div class="metric-container">
                <div style="font-size: 11px; font-weight: bold; color: #8A6F5C; text-transform: uppercase; letter-spacing: 0.08em;">Trip Duration</div>
                <div style="font-size: 24px; font-weight: bold; color: {TEXT_COLOR};">{duration_days} Days</div>
            </div>
            """,
            unsafe_allow_html=True
        )
    with m_col2:
        st.markdown(
            f"""
            <div class="metric-container">
                <div style="font-size: 11px; font-weight: bold; color: #8A6F5C; text-transform: uppercase; letter-spacing: 0.08em;">Estimated Budget</div>
                <div style="font-size: 24px; font-weight: bold; color: {TEXT_COLOR};">${st.session_state.budget * duration_days} Total</div>
            </div>
            """,
            unsafe_allow_html=True
        )
    with m_col3:
        st.markdown(
            f"""
            <div class="metric-container">
                <div style="font-size: 11px; font-weight: bold; color: #8A6F5C; text-transform: uppercase; letter-spacing: 0.08em;">Destination</div>
                <div style="font-size: 24px; font-weight: bold; color: {TEXT_COLOR}; truncate;">{st.session_state.destination.split(',')[0]}</div>
            </div>
            """,
            unsafe_allow_html=True
        )

    st.markdown("<div style='margin-bottom: 25px;'></div>", unsafe_allow_html=True)

    # Columns layout
    col_left, col_right = st.columns([1.2, 1], gap="large")

    # Left Column: Map & Day-by-Day Itinerary
    with col_left:
        st.markdown("### 📍 Location Map")
        if st.session_state.coords:
            lat, lon = st.session_state.coords
            df = pd.DataFrame({"lat": [lat], "lon": [lon]})
            st.map(df, zoom=11, width="stretch")
        else:
            st.warning("⚠️ Map coordinates could not be loaded dynamically. Displaying itinerary below.")

        st.markdown("### 📅 Day-by-Day Itinerary")
        itinerary_text = st.session_state.sections.get("itinerary", "No itinerary generated.")
        
        # Split Itinerary into individual day tabs
        day_splits = parse_itinerary_days(itinerary_text)
        if day_splits:
            day_tabs = st.tabs([day[0] for day in day_splits])
            for tab, (day_title, day_content) in zip(day_tabs, day_splits):
                with tab:
                    # Parse and format mock bookings inside day content if any
                    st.markdown(format_mock_bookings(day_content), unsafe_allow_html=True)
        else:
            st.markdown(format_mock_bookings(itinerary_text), unsafe_allow_html=True)

    # Right Column: Tabs (Hotels & Dining, Budget Details, Weather, Refinement Chat)
    with col_right:
        st.markdown("### 📊 Details & AI Assistant")
        
        info_tabs = st.tabs(["🏨 Stay & Dine", "💰 Budget Analysis", "🌤️ Weather & Packing", "💬 Refine with AI"])
        
        # Tab 1: Accommodation & Restaurants
        with info_tabs[0]:
            st.markdown("#### 🏨 Hotel Suggestions")
            hotels_content = st.session_state.sections.get("hotels", "No hotel recommendations.")
            st.markdown(format_mock_bookings(hotels_content), unsafe_allow_html=True)
            
            st.markdown("---")
            st.markdown("#### 🍴 Restaurant Recommendations")
            restaurants_content = st.session_state.sections.get("restaurants", "No restaurant recommendations.")
            st.markdown(format_mock_bookings(restaurants_content), unsafe_allow_html=True)
            
        # Tab 2: Budget Details
        with info_tabs[1]:
            st.markdown("#### 💰 Cost Breakdown")
            budget_content = st.session_state.sections.get("budget", "No budget breakdown available.")
            st.markdown(format_mock_bookings(budget_content), unsafe_allow_html=True)
            
        # Tab 3: Weather Details
        with info_tabs[2]:
            st.markdown("#### 🌤️ Weather Forecast & Packing Tips")
            weather_content = st.session_state.sections.get("weather", "No weather information.")
            st.markdown(format_mock_bookings(weather_content), unsafe_allow_html=True)

        # Tab 4: Refinement Chat
        with info_tabs[3]:
            st.markdown("#### 💬 Ask TravelGenie to Refine Your Trip")
            st.caption("Example: 'Suggest vegetarian restaurants', 'Decrease budget limit', or 'Make Day 2 more historical'.")
            
            # Displays refinement chat history
            chat_container = st.container(height=350)
            with chat_container:
                # Loop through custom chat logs (ignoring initial launch logs to keep clean)
                for role, msg_text in st.session_state.display_history[2:]:
                    with st.chat_message(role):
                        st.markdown(format_mock_bookings(msg_text), unsafe_allow_html=True)
            
            # Chat input
            refinement_input = st.chat_input("Suggest changes to your itinerary...")
            if refinement_input:
                # Add to display & conversation logs
                st.session_state.display_history.append(("user", refinement_input))
                st.session_state.chat_history.append(HumanMessage(content=refinement_input))
                
                with chat_container:
                    with st.chat_message("user"):
                        st.markdown(refinement_input)
                
                with chat_container:
                    with st.chat_message("assistant"):
                        with st.spinner("Re-structuring your dashboard..."):
                            try:
                                result = st.session_state.executor.invoke({
                                    "input": refinement_input,
                                    "chat_history": st.session_state.chat_history
                                })
                                answer = extract_text_output(result["output"])
                                st.markdown(format_mock_bookings(answer), unsafe_allow_html=True)
                                
                                # Update agent history state
                                st.session_state.chat_history.append(AIMessage(content=answer))
                                st.session_state.display_history.append(("assistant", answer))
                                
                                # Parse new response and update dashboard sections
                                st.session_state.raw_response = answer
                                st.session_state.sections = parse_sections(answer)
                                
                                # Rerun to update tabs and lists dynamically
                                st.rerun()
                            except Exception as e:
                                st.error(f"The Gemini AI model is currently experiencing high demand. Please try again in a few seconds. Error: {e}")