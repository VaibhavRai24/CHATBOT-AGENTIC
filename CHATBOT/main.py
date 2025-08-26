from typing import TypedDict, Annotated, Optional
from langgraph.graph import add_messages, StateGraph, END
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, ToolMessage, AIMessageChunk
from dotenv import load_dotenv
from langchain_community.tools.tavily_search import TavilySearchResults
from fastapi import FastAPI, Query
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import json
from uuid import uuid4
from langchain_core.tools import tool
import requests
from langgraph.checkpoint.memory import InMemorySaver

load_dotenv()

# Checkpointer
memory = InMemorySaver()

class State(TypedDict):
    messages:Annotated[list, add_messages]
    
search_tool = TavilySearchResults(
    max_results=5
)
@tool
def get_stock_price(symbol: str) -> dict:
    """
    Use this tool ONLY to fetch the latest live stock price of a company.
    Input must be a stock ticker symbol (e.g., 'AAPL' for Apple, 'TSLA' for Tesla).
    Do NOT use search engines for stock prices.
    """
    url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={symbol}&apikey=BZZ2I89IVW76Q6UJ"
    r = requests.get(url)
    return r.json()

tools = [search_tool, get_stock_price]

llm = ChatGroq(model="llama-3.1-8b-instant")

llm_with_tools = llm.bind_tools(tools=tools)

async def model(state:State):
    result = await llm_with_tools.ainvoke(
        state["messages"]
    )
    return {"messages": [result] if not isinstance(result, list) else result}  
    
async def tool_router(state:State):
    """Router to handle decisions wheather to call a tool or not"""
    last_message = state["messages"][-1]
    if "stock price" in last_message or "share price" in last_message:
        return "tool_node"
    last_message_obj = state["messages"][-1]
    if hasattr(last_message_obj, "tool_calls") and len(last_message_obj.tool_calls) > 0:
        return "tool_node"
    else:
        return END
    
async def tool_node(state:State):
    """This is basically the tool node that handles the tool calls"""
    tool_calls  = state["messages"][-1].tool_calls
    tool_messages = []
    for tool_call in tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]
        tool_id = tool_call["id"]
        
        
        if tool_name == "tavily_search_results_json":
            search_results = await search_tool.ainvoke(tool_args)
            tool_message = ToolMessage(
                content = str(search_results),
                tool_call_id = tool_id,
                name = tool_name
            )
        elif tool_name == "get_stock_price":
            stock_data = get_stock_price.invoke(tool_args)   
            tool_message = ToolMessage(
                content=str(stock_data),
                tool_call_id=tool_id,
                name=tool_name
            )

        else:
            tool_message = ToolMessage(
                content=f"Tool {tool_name} not implemented.",
                tool_call_id=tool_id,
                name=tool_name
            )
        tool_messages.append(tool_message)
        
    return {"messages" : tool_messages}

graph_builder = StateGraph(State)
graph_builder.add_node("model", model)
graph_builder.add_node("tool_node", tool_node)
graph_builder.set_entry_point("model")

graph_builder.add_conditional_edges("model", tool_router)
graph_builder.add_edge("tool_node", "model")

graph = graph_builder.compile(checkpointer=memory)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Type"]
)

def serialise_ai_message_chunk(chunk): 
    if(isinstance(chunk, AIMessageChunk)):
        return chunk.content
    else:
        raise TypeError(
            f"Object of type {type(chunk).__name__} is not correctly formatted for serialisation"
        )


async def generate_chat_responses(message: str, checkpoint_id: Optional[str] = None):
    is_new_conversation = checkpoint_id is None
    
    if is_new_conversation:
        new_checkpoint_id = str(uuid4())

        config = {
            "configurable": {
                "thread_id": new_checkpoint_id
            }
        }
        
        events = graph.astream_events(
            {"messages": [HumanMessage(content=message)]},
            version="v2",
            config=config
        )
        
        yield f"data: {json.dumps({'type': 'checkpoint', 'checkpoint_id': new_checkpoint_id})}\n\n"
    else:
        config = {
            "configurable": {
                "thread_id": checkpoint_id
            }
        }

        events = graph.astream_events(
            {"messages": [HumanMessage(content=message)]},
            version="v2",
            config=config
        )
        
    async for event in events:
        event_type = event["event"]
        
        if event_type == "on_chat_model_stream":
            chunk_content = serialise_ai_message_chunk(event["data"]["chunk"])
            payload = {"type": "content", "content": chunk_content}
            yield f"data: {json.dumps(payload)}\n\n"
            
        elif event_type == "on_chat_model_end":
            output = event["data"]["output"]

            if hasattr(output, "tool_calls") and output.tool_calls:
                for call in output.tool_calls:
                    tool_name = call["name"]

                    # Generic tool start event
                    payload = {
                        "type": "tool_start",
                        "tool": tool_name
                    }
                    yield f"data: {json.dumps(payload)}\n\n"

                    # Keep old Tavily-specific search_start (optional)
                    if tool_name == "tavily_search_results_json":
                        search_query = call["args"].get("query", "")
                        payload = {"type": "search_start", "query": search_query}
                        yield f"data: {json.dumps(payload)}\n\n"

                
        elif event_type == "on_tool_end":
            tool_name = event["name"]
            output = event["data"]["output"]

            if tool_name == "tavily_search_results_json":
                if isinstance(output, list):
                    urls = []
                    for item in output:
                        if isinstance(item, dict) and "url" in item:
                            urls.append(item["url"])
                    payload = {"type": "search_results", "urls": urls}
                    yield f"data: {json.dumps(payload)}\n\n"

            elif tool_name == "get_stock_price":
                payload = {
                    "type": "stock_result",
                    "output": output
                }
                yield f"data: {json.dumps(payload)}\n\n"

            else:
                # Generic tool end (for future tools)
                payload = {
                    "type": "tool_end",
                    "tool": tool_name,
                    "output": output
                }
                yield f"data: {json.dumps(payload)}\n\n"

    
    yield f"data: {json.dumps({'type': 'end'})}\n\n"

@app.get("/chat_stream/{message}")
async def chat_stream(message: str, checkpoint_id: Optional[str] = Query(None)):
    return StreamingResponse(
        generate_chat_responses(message, checkpoint_id), 
        media_type="text/event-stream"
    )