# 🌍 TravelGenie — Multi-Agent AI Travel Planner

TravelGenie is a team of AI agents that plans trips together. A supervisor reads your request and sends it to specialist agents (Research, Weather, Budget, Booking), which run in parallel. An itinerary writer then combines their findings into one day-by-day plan, where every fact links to the source it came from.

The Research agent runs an advanced **RAG pipeline** over a local **ChromaDB** vector database that holds curated destination guides, your own uploaded documents, and cached web results.

---

## ✨ Features

- 🤖 **Multi-agent orchestration** with LangGraph: a supervisor routes each request, and the specialists run in parallel
- 📚 **Advanced RAG**: hybrid search, multi-query rewriting, cross-encoder reranking, corrective web fallback, inline citations
- 📄 **Bring your own documents**: upload PDFs or notes (bookings, visa rules, guidebooks) and the agents use them
- ⚡ **Live streaming UI**: watch each agent work in real time, then read the answer token by token
- 🔗 **Clickable citations**: every `[n]` opens the exact passage it came from
- 🌦️ Live 5-day forecast, 💰 cost breakdown, 🎟️ simulated bookings
- 🔁 **Conversation memory**: revise a plan ("make it cheaper", "swap day 2"), and history survives restarts
- 🌗 Light and dark themes, responsive on mobile

---

## 🧠 Architecture

```text
                    React + TypeScript (Vite, Tailwind)
                                │  SSE stream
                                ▼
                         FastAPI  /api/chat
                                │
                     ┌──── Supervisor ────┐   (routes + extracts the trip brief)
                     ▼        ▼       ▼       ▼
                 Research  Weather  Budget  Booking     ← run in parallel
                     │
                     ▼
              RAG pipeline ──► ChromaDB + BM25
                     │
                     └──────────► Itinerary writer ──► cited answer
```

### The RAG pipeline (`backend/rag/pipeline.py`)

1. **Query understanding**: the LLM rewrites the question into several search queries and detects the destination.
2. **Hybrid retrieval**: dense vector search (ChromaDB, `bge-small-en-v1.5` embeddings) plus BM25 keyword search, both filtered by destination metadata.
3. **Reciprocal Rank Fusion**: merges all the result lists.
4. **Cross-encoder reranking**: `ms-marco-MiniLM` scores every (query, chunk) pair.
5. **Corrective RAG**: if local evidence is weak, it searches the web (Tavily) and caches the results in the vector DB for next time.
6. **Context expansion**: pulls in each hit's neighbouring chunks.
7. **Citations**: sources are numbered, and the writer must cite them as `[n]`.

Chunking is structure-aware: markdown splits on headings first, and every chunk keeps its section path, e.g. `Paris > Major sights > Louvre`. Embeddings and reranking run **locally** (ONNX via fastembed), so they need no GPU and no extra API key.

---

## 🛠️ Tech Stack

| Layer | Tech |
|---|---|
| Frontend | React 19, TypeScript, Vite, Tailwind CSS, react-markdown |
| API | FastAPI, Server-Sent Events, Uvicorn |
| Agents | LangGraph, LangChain, Groq (`gpt-oss-20b` for routing/specialists, `gpt-oss-120b` for the writer) |
| Vector DB | ChromaDB (persistent, local) |
| Retrieval | fastembed (embeddings + cross-encoder), rank-bm25 |
| Memory | LangGraph SQLite checkpointer |
| Tools | Tavily web search, OpenWeatherMap |

---

## 📂 Project Structure

```text
TravelGenie/
├── backend/
│   ├── agents/      # supervisor, specialists, tools, graph state
│   ├── rag/         # ingest, vector store, retrieval pipeline, seeding
│   ├── api/main.py  # FastAPI app (chat stream, documents, search)
│   ├── config.py
│   └── llm.py
├── data/guides/     # curated destination guides (auto-indexed)
├── frontend/        # React app
├── storage/         # vector DB, uploads, chat memory (created at runtime)
├── requirements.txt
└── .env.example
```

---

## 🚀 Getting Started

You need **Python 3.11+** and **Node.js 20+**.

### 1. Backend

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env              # then add your keys
uvicorn backend.api.main:app --reload --port 8000
```

The first start downloads the embedding and reranker models (~150MB) and indexes `data/guides/`.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**.

### Production build

Run `npm run build` inside `frontend/`. FastAPI then serves the built app directly at http://localhost:8000.

---

## 🔑 Environment Variables

| Variable | Required | Purpose |
|---|---|---|
| `GROQ_API_KEY` | ✅ | LLM for all agents |
| `TAVILY_API_KEY` | optional | Web-search fallback for RAG |
| `OPENWEATHERMAP_API_KEY` | optional | Live forecasts |
| `GROQ_MODEL` / `GROQ_FAST_MODEL` / `GROQ_WRITER_MODEL` | optional | Override the models used by the specialists, the router and the writer |

Without the optional keys, the app still works; it skips web search or live weather and warns when an answer couldn't be verified.

> **Groq free tier:** about 8,000 tokens per minute *per model*. TravelGenie splits the work across two models and retries automatically. If you send several full itineraries back-to-back you may still need to wait a minute.

---

## 📚 Adding knowledge

- **Guides**: drop a markdown file in `data/guides/` with front matter (`destination`, `title`). It's indexed on the next start.
- **Your documents**: use the **Knowledge base** page in the app to upload files and tag them with a destination.
- **Retrieval inspector**: on the same page, run a query and see every stage of the pipeline, with scores.

---

## 🔌 API

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/chat` | Run the agent team (SSE: `agent`, `token`, `final`, `error`) |
| `GET` | `/api/threads/{id}` | Restore a conversation |
| `GET/POST` | `/api/documents` | List / upload knowledge |
| `DELETE` | `/api/documents/{doc_id}` | Remove a document |
| `POST` | `/api/search` | Run the RAG pipeline directly |
| `GET` | `/api/health` | Status and missing keys |

Interactive docs are at http://localhost:8000/docs.

---

## 💡 Future Enhancements

- 🏨 Real hotel booking integration
- 🗺️ Map and visual itinerary view
- 👥 Collaborative / group trip planning
- 🔄 Cost-optimisation agent loop
- 💸 Expense tracker
- 📄 PDF itinerary download
- 🌐 Multi-language support

---

## 🤝 Contributing

1. Fork the repository.
2. Create a feature branch.
3. Commit your changes.
4. Push your branch and open a Pull Request.

---

⭐ If you found this project useful, consider giving it a star on GitHub!
