"""
main.py (updated)
-----------------
FastAPI + LangGraph backend with tool calling.
Adds new free tools from tools.py (weather, FX, crypto, holidays, jokes).

ENV required:
  - GROQ_API_KEY=<your groq key>
  - (optional) ALPHAVANTAGE_API_KEY=<for get_stock_price>

Run:
  uvicorn main:app --reload --port 8000
"""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from typing import Annotated, Dict, List, Literal, Optional, TypedDict

from dotenv import load_dotenv
load_dotenv()

import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse

from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langchain_groq import ChatGroq

from langchain_community.tools.tavily_search import TavilySearchResults
from langgraph.graph import StateGraph, END, START
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph.message import add_messages

# ---- Import our new tools ----
from tools import (
    get_weather,
    get_exchange_rate,
    get_crypto_spot_price,
    get_public_holidays,
    get_joke,
    get_stock_price,
)

# ---------- LLM ----------
llm = ChatGroq(model="llama-3.1-8b-instant", temperature=0)

# ---------- Tools ----------
search_tool = TavilySearchResults(max_results=5)
ALL_TOOLS = [search_tool, get_weather, get_exchange_rate, get_crypto_spot_price, get_public_holidays, get_joke, get_stock_price]
tool_map = {t.name: t for t in ALL_TOOLS}
model = llm.bind_tools(ALL_TOOLS)

# ---------- LangGraph State ----------
class State(TypedDict):
    messages: Annotated[List, add_messages]

def _get_last_ai_tool_calls(messages: List):
    if not messages:
        return []
    last = messages[-1]
    return getattr(last, "tool_calls", []) or []

async def call_tool(name: str, args: dict):
    tool_ref = tool_map.get(name)
    if tool_ref is None:
        return {"error": f"Unknown tool: {name}", "name": name}
    try:
        # All LangChain tools support ainvoke
        return await tool_ref.ainvoke(args)
    except Exception as e:
        return {"error": str(e), "name": name}

async def model_node(state: State, config: RunnableConfig):
    return {"messages": [await model.ainvoke(state["messages"], config=config)]}

async def tool_node(state: State, config: RunnableConfig):
    last = state["messages"][-1]
    results = []
    for tc in getattr(last, "tool_calls", []) or []:
        name = tc.get("name")
        args = tc.get("args") or {}
        result = await call_tool(name, args)
        results.append(ToolMessage(content=json.dumps(result), name=name, tool_call_id=tc["id"]))
    return {"messages": results}

def route_tools(state: State) -> Literal["tool_node", "__end__"]:
    # Route to tool node only if last AI message requested tools
    return "tool_node" if _get_last_ai_tool_calls(state["messages"]) else "__end__"

graph_builder = StateGraph(State)
graph_builder.add_node("model", model_node)
graph_builder.add_node("tool_node", tool_node)
graph_builder.add_edge(START, "model")
graph_builder.add_conditional_edges("model", route_tools, {"tool_node": "tool_node", "__end__": END})
graph_builder.add_edge("tool_node", "model")
memory = MemorySaver()
app_graph = graph_builder.compile(checkpointer=memory)

# ---------- FastAPI ----------
app = FastAPI(title="Agentic Backend with Free Tools")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    return {"ok": True}

async def _sse(stream):
    async for event in stream:
        if "messages" in event:
            # Only pick the *latest* message (last one)
            last_msg = event["messages"][-1]
            if hasattr(last_msg, "content") and isinstance(last_msg.content, str) and last_msg.type == "ai":
                yield f"data: {json.dumps({'type': 'content', 'text': last_msg.content})}\n\n"
        elif "event" in event:
            ev = event["event"]
            if ev.get("type") == "on_tool_start":
                yield f"data: {json.dumps({'type': 'tool_start', 'tool': ev.get('name')})}\n\n"
            elif ev.get("type") == "on_tool_end":
                yield f"data: {json.dumps({'type': 'tool_end', 'tool': ev.get('name')})}\n\n"
    yield "data: {\"type\": \"end\"}\n\n"


@app.get("/chat_stream/{message}")
async def chat_stream(message: str, thread_id: Optional[str] = None):
    """
    SSE endpoint used by the frontend. Creates/continues a thread in the graph.
    """
    if not thread_id:
        thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    stream = app_graph.astream({"messages": [HumanMessage(content=message)]}, config, stream_mode="values")
    return StreamingResponse(_sse(stream), media_type="text/event-stream")

# Convenience non-streaming endpoint for testing
@app.post("/chat")
async def chat(payload: Dict[str, str]):
    text = payload.get("message", "")
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    final = await app_graph.ainvoke({"messages": [HumanMessage(content=text)]}, config)
    # Extract last AI message
    msg = next((m for m in final["messages"][::-1] if getattr(m, "type", "") == "ai"), None)
    return JSONResponse({"reply": getattr(msg, "content", "")})

# Backwards compatibility for existing frontend imports
graph = app_graph
