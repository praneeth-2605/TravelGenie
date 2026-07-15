import os
from langchain_classic.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI
from agent.tools import get_all_tools

SYSTEM_PROMPT = """You are TravelGenie, an expert trip-planning agent.

1. Produce a DAY-BY-DAY itinerary for the destination and dates given.
   Use the search tool for real, current attractions/neighborhoods, and the
   weather tool to ground timing and packing advice.
2. When the user gives new constraints later (budget, dates, pace), REVISE
   the existing plan instead of starting over.
3. Use the mock booking tool to "lock in" 1-2 representative bookings.
   Always state clearly these are simulated, not real, bookings.
4. On a first-time itinerary, always end with two sections: "Packing List"
   and "Weather Advisory", both derived from the actual forecast/season.

Use markdown, structure by Day 1 / Day 2 / ..., morning/afternoon/evening.
"""

def build_agent_executor(groq_api_key: str | None = None) -> AgentExecutor:
    api_key = groq_api_key or os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY is not set.")

    llm = ChatOpenAI(
        model=os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"),
        api_key=api_key,
        base_url="https://api.groq.com/openai/v1",
        temperature=0.4,
        max_tokens=4000,
    )
    tools = get_all_tools()
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        MessagesPlaceholder("chat_history", optional=True),
        ("human", "{input}"),
        MessagesPlaceholder("agent_scratchpad"),
    ])
    agent = create_tool_calling_agent(llm, tools, prompt)
    return AgentExecutor(agent=agent, tools=tools, verbose=False,
                          max_iterations=8, handle_parsing_errors=True)
