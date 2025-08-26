import streamlit as st
import sseclient
import urllib.parse
import json
import uuid
from app import graph
from langchain_core.messages import HumanMessage

st.set_page_config(page_title="AI Chat with LangGraph", page_icon="🤮", layout="centered")
st.title("Where should we begin 🤮")
st.sidebar.title("Chat with MaxAGE")
st.sidebar.header("My Conversations")

def generate_thread_id():
    thread_id = str(uuid.uuid4())
    return thread_id

def add_thread(thread_id):
    if thread_id not in st.session_state["chat_threads"]:
        st.session_state["chat_threads"].append(thread_id)
        
def reset_thread():
    thread_id = generate_thread_id() 
    st.session_state["checkpoint_id"] = thread_id
    add_thread(st.session_state["checkpoint_id"])
    st.session_state["messages"] = []
    
def load_converastion(thread_id):
    state = graph.get_state(config={'configurable': {'thread_id': thread_id}})
    return state.values.get('messages', [])

if st.sidebar.button("New chat"):
    reset_thread()
        
# Backend URL
BACKEND_URL = "http://127.0.0.1:8000/chat_stream/"

# Session State to keep messages
if "messages" not in st.session_state:
    st.session_state["messages"] = []
if "checkpoint_id" not in st.session_state:
    st.session_state["checkpoint_id"] = generate_thread_id()
    
if "chat_threads" not in st.session_state:
    st.session_state["chat_threads"] = []


add_thread(st.session_state["checkpoint_id"])

for thread_id in st.session_state['chat_threads'][::-1]:
    if st.sidebar.button(str(thread_id)):
        st.session_state['checkpoint_id'] = thread_id
        messages = load_converastion(thread_id)

        temp_messages = []

        for msg in messages:
            if isinstance(msg, HumanMessage):
                role='user'
            else:
                role='assistant'
            temp_messages.append({'role': role, 'content': msg.content})

        st.session_state['message_history'] = temp_messages

for message in st.session_state["messages"]:
    role = message["role"]
    content = message["content"]
    if role == "user":
        st.chat_message("user").write(content)
    else:
        st.chat_message("assistant").write(content)


if user_input := st.chat_input("Type your message..."):
    # Add user message to history
    st.session_state["messages"].append({"role": "user", "content": user_input})
    st.chat_message("user").write(user_input)


    full_url = f"{BACKEND_URL}{urllib.parse.quote(user_input)}"
    if st.session_state["checkpoint_id"]:
        full_url += f"?checkpoint_id={st.session_state['checkpoint_id']}"

    
    client = sseclient.SSEClient(full_url)

 
    with st.chat_message("assistant"):
        placeholder = st.empty()
        response_text = ""

        for event in client:
            if event.event == "message":
                data = json.loads(event.data)  # <-- FIXED here
                event_type = data.get("type")

                if event_type == "checkpoint":
                    st.session_state["checkpoint_id"] = data["checkpoint_id"]

                elif event_type == "content":
                    response_text += data["content"]
                    placeholder.write(response_text)
                    
                elif event_type == "tool_start":
                    tool = data["tool"]
                    placeholder.write(response_text + f"\n\n⚙️ Using tool: **{tool}**")

                elif event_type == "search_start":
                    placeholder.write(response_text + f"\n\n🔍 Searching for: {data['query']}")

                elif event_type == "search_results":
                    urls = data["urls"]
                    links = "\n".join([f"[Result]({url})" for url in urls])
                    placeholder.write(response_text + "\n\n" + links)

                elif event_type == "end":
                    break

        
        st.session_state["messages"].append({"role": "assistant", "content": response_text})
