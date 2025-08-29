🤖 Chatbot Agentic with LangGraph + FastAPI + Streamlit
![Uploading image.png…]()

An Agentic AI Chatbot powered by LangGraph, Groq LLM, and a suite of free tools.
It supports multi-turn conversations, tool usage tracking, and a clean chat UI built with Streamlit.

🚀 Features

FastAPI Backend (main_updated.py)

Handles conversation flow via LangGraph.

SSE streaming for real-time chat.

Integrates with Groq LLM.

Supports multiple tool calls.

Streamlit Frontend (frontend.py)

Modern chat interface.

Threaded conversations with session tracking.

Sidebar showing conversation history.

Tool usage displayed live during chat.

Built-in Tools (tools.py)

🌦️ Weather (via Open-Meteo)

💱 Currency Exchange Rates (via Frankfurter)

🪙 Crypto Spot Price (via Coinbase)

📅 Public Holidays (via Nager.Date)

😂 Jokes (via JokeAPI)

📈 Stock Prices (via AlphaVantage, requires API key)

🔍 Web Search (via Tavily, free search API)

🛠️ Tech Stack

LangGraph — Orchestrating LLM and tools

LangChain — LLM & tool integration

FastAPI — Backend API with SSE streaming

Streamlit — Interactive chat frontend

Groq LLM — Ultra-fast inference (llama-3.1-8b-instant)

Python 3.10+

📂 Project Structure
CHATBOT-AGENTIC/
│
├── frontend.py         # Streamlit UI
├── main_updated.py     # FastAPI backend (LangGraph + LLM)
├── tools.py            # Free tools (weather, jokes, FX, etc.)
├── .env                # Environment variables (ignored in Git)
├── .gitignore          # Ignore sensitive files
└── README.md           # Project docs

⚙️ Setup & Installation
1️⃣ Clone repo
git clone https://github.com/<your-username>/CHATBOT-AGENTIC.git
cd CHATBOT-AGENTIC

2️⃣ Create virtual environment
python -m venv .venv
source .venv/bin/activate   # Mac/Linux
.venv\Scripts\activate      # Windows

3️⃣ Install dependencies
pip install -r requirements.txt

4️⃣ Setup environment variables

Create a .env file (⚠️ don’t commit this file to GitHub):

GROQ_API_KEY=your_groq_api_key
ALPHAVANTAGE_API_KEY=your_alphavantage_key   # optional

▶️ Running the App
Start the backend (FastAPI)
uvicorn main_updated:app --reload --port 8000

Start the frontend (Streamlit)
streamlit run frontend.py

🎯 Usage

Open the Streamlit app in your browser.

Start a new chat or continue an existing thread.

Ask anything:

"What’s the weather in Bengaluru?"

"Convert 100 USD to INR"

"Tell me a programming joke"

"Give me stock price of AAPL"

The assistant will show:

Responses in the chat.

Tools it used in real-time.

A summary of tools in the sidebar.

🔒 Security

.env file is gitignored.

API keys are loaded via python-dotenv.

GitHub push protection prevents secrets from leaking.


🤝 Contributing

Fork the repo

Create a feature branch

Submit a PR

📜 License

MIT License © 2025 Vaibhav Rai
