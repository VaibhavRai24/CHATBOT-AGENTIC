import streamlit as st
import sseclient
import urllib.parse
import json
import uuid
from main_updated import app_graph
from langchain_core.messages import HumanMessage

# ---------------------- UI SETUP ----------------------
st.set_page_config(page_title="AI Chat with LangGraph", page_icon="🤖", layout="centered")
st.title("Where should we begin 🤖")
st.sidebar.title("Chat with MaxAGE")
st.sidebar.header("My Conversations")

# ---------------------- SESSION HELPERS ----------------------
def generate_thread_id():
    return str(uuid.uuid4())

def add_thread(thread_id):
    if thread_id not in st.session_state["chat_threads"]:
        st.session_state["chat_threads"].append(thread_id)
        
def reset_thread():
    thread_id = generate_thread_id() 
    st.session_state["thread_id"] = thread_id
    add_thread(thread_id)
    st.session_state["messages"] = []
    
def load_conversation(thread_id):
    state = app_graph.get_state(config={'configurable': {'thread_id': thread_id}})
    return state.values.get('messages', [])

# ---------------------- INITIALIZE SESSION STATE ----------------------
if "messages" not in st.session_state:
    st.session_state["messages"] = []
if "thread_id" not in st.session_state:
    st.session_state["thread_id"] = generate_thread_id()
if "chat_threads" not in st.session_state:
    st.session_state["chat_threads"] = []

add_thread(st.session_state["thread_id"])

# ---------------------- SIDEBAR ----------------------
if st.sidebar.button("➕ New chat"):
    reset_thread()

for thread_id in st.session_state['chat_threads'][::-1]:
    if st.sidebar.button(str(thread_id)):
        st.session_state['thread_id'] = thread_id
        messages = load_conversation(thread_id)

        temp_messages = []
        for msg in messages:
            role = "user" if isinstance(msg, HumanMessage) else "assistant"
            temp_messages.append({"role": role, "content": msg.content})
        st.session_state["messages"] = temp_messages

# ---------------------- SHOW CHAT HISTORY ----------------------
for message in st.session_state["messages"]:
    st.chat_message(message["role"]).write(message["content"])

# ---------------------- BACKEND URL ----------------------
BACKEND_URL = "http://127.0.0.1:8000/chat_stream/"

# ---------------------- USER INPUT ----------------------
if user_input := st.chat_input("Type your message..."):
    st.session_state["messages"].append({"role": "user", "content": user_input})
    st.chat_message("user").write(user_input)

    full_url = f"{BACKEND_URL}{urllib.parse.quote(user_input)}"
    if st.session_state["thread_id"]:
        full_url += f"?thread_id={st.session_state['thread_id']}"

    client = sseclient.SSEClient(full_url)

    with st.chat_message("assistant"):
        placeholder = st.empty()
        response_text = ""
        used_tools = []   # Track tools used in this reply

        for event in client:
            if event.event == "message":
                data = json.loads(event.data)
                event_type = data.get("type")

                if event_type == "content":
                    # Stream only incremental assistant text
                    new_text = data.get("text", "")
                    delta = new_text[len(response_text):]
                    response_text = new_text
                    placeholder.write(response_text)

                elif event_type == "tool_start":
                    tool = data.get("tool")
                    if tool and tool not in used_tools:
                        used_tools.append(tool)
                    placeholder.write(response_text + f"\n\n⚙️ Using tool: **{tool}**")

                elif event_type == "tool_end":
                    tool = data.get("tool")
                    placeholder.write(response_text + f"\n\n✅ Tool finished: **{tool}**")

                elif event_type == "end":
                    break

        # Save assistant reply
        st.session_state["messages"].append({"role": "assistant", "content": response_text})

        # Sidebar: show which tools were used
        if used_tools:
            st.sidebar.write(f"🛠 Tools used for this reply: {', '.join(used_tools)}")



