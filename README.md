# 🌍 TravelGenie — Multi-Agent AI Travel Planner

Tell TravelGenie where you're going and for how long. A team of AI agents finds **real hostels, hotels and sights**, checks the weather, researches the destination, and builds **three complete trip options**, each with a day-by-day itinerary:

| | Option | What you get |
|---|---|---|
| 💰 | **Budget** | The cheapest sensible trip: hostels, street food, public transport |
| 💎 | **Luxury** | Premium comfort: top hotels, fine dining, private transfers |
| 🎯 | **Your budget** | Fitted to *your* budget range, with the best-matched hostel or hotel |

**Choose a plan** and TravelGenie expands it into a detailed version (where to eat each day with prices, how to get around, daily spend and a booking checklist) and the chat switches to discussing *your* plan.

After every request you get separate sections: **Overview, Getting there (flight / train / bus / car / ferry), Hotels, Itinerary, Weather, Web search and Map**, and you can export to **PDF, calendar (.ics) or Markdown**.

---

## ✨ Features

- 👤 **Accounts**: email + password sign-up, "Continue with Google", secure httpOnly sessions, log out everywhere, account deletion
- 📱 **Installable app**: add TravelGenie to your phone's home screen; saved trips open offline
- 🔗 **Share trips**: public read-only links and one-tap WhatsApp sharing (chats and private documents are never shared)
- 🎫 **Booking links**: Google Flights, IRCTC, redBus, Booking.com and Google Maps, pre-filled from the plan
- ₹ **Made for India**: Indian number formats (₹1,50,000) and per-person or total budgets
- ⚖️ **Fair use and compliance**: daily AI request limits, Privacy Policy and Terms (DPDP Act 2023), consent at sign-up, one-click data download
- 🔒 **Privacy**: uploaded documents are private to their owner (never used in other users' answers), and deleting a trip or an account also deletes its chat history and uploads
- ⚙️ **User settings**: home city, home currency, usual travellers, typical budget range, travel style, pace, interests, dietary needs, light/dark theme. These are used as defaults for every plan.
- 📊 **Dashboard**: your trips with prices for all three options, stats, upcoming-trip countdown, favourites
- 🎯 **Choose a plan** → detailed day-by-day version (meals, getting around, daily spend, booking checklist) + chat focused on it
- 🚆 **Every way to get there**: flights, trains, buses, self-drive, taxi and ferries compared by price, time, route and where to book
- 🧩 **Separate sections** after each request: Overview, Getting there, Hotels, Itinerary, Weather, Web search, Map
- 🤖 **Nine specialised agents** coordinated by a supervisor (LangGraph), running in parallel
- 🏨 **Real places**: stays (by price tier, with listed prices) and sights from Wikivoyage, plus geocoding from OpenStreetMap
- 🗺️ **Interactive map** with day-coloured pins and your stay
- 📚 **Advanced RAG** over a ChromaDB knowledge base: hybrid search, multi-query, reranking, citations, web fallback
- 🔁 **Conversational refinement**: "make it cheaper", "add a beach day", "make the luxury option more special"
- 📄 **Exports**: PDF (one option or all three), calendar file for Google/Apple/Outlook, Markdown

---

## 🧠 The agent team

```text
                       ┌──► Research   (RAG knowledge base + web)      ──┐
                       ├──► Weather    (live forecast / seasonal)        ─┤
  you ─► Supervisor ───┼──► Stays      (hostels & hotels by price tier)  ─┼─► Planner ─► 3 options + day plan
                       ├──► Sightseeing (local sights & activities)      ─┤
                       ├──► Transport  (flight/train/bus/car/ferry)      ─┤
                       ├──► Web search (what to know before you go)      ─┤
                       └──► Booking    (simulated bookings)              ──┘   Writer ─► cited answers
```

| Agent | Job |
|---|---|
| **Supervisor** | Understands the request, fills gaps from your settings, decides the intent (plan / revise / question / book / chat) and which agents to call |
| **Research** | Hybrid RAG over curated guides, your uploaded documents and cached web results |
| **Weather** | Live 5-day forecast, or seasonal norms when the trip is further out |
| **Stays** | Real places to stay from Wikivoyage, grouped Budget / Mid-range / Luxury with listed prices |
| **Sightseeing** | Real sights and activities with coordinates and opening hours, matched to your interests |
| **Transport** | Compares every way to get there from your city (flight, train, bus, car, ferry): price range, duration, route, where to book |
| **Web search** | Live web results (Tavily), or the destination's Wikivoyage guide: safety, getting around, money, etiquette |
| **Planner** | Builds the three options (travel mode, costs, breakdown, best stay, highlights) and the shared day-by-day itinerary as structured JSON; checks "Your budget" really fits your range |
| **Concierge** | When you choose an option: expands it into meals, getting around, daily spend and a booking checklist |
| **Writer** | Answers questions with inline citations |

All the output formats (cards, timeline, map, PDF, calendar, Markdown) are generated from the planner's one structured plan.

---

## 🛠️ Tech Stack

| Layer | Tech |
|---|---|
| Frontend | React 19, TypeScript, Vite, Tailwind CSS, React Router, Leaflet (OpenStreetMap) |
| API | FastAPI, Server-Sent Events (a Vercel Python function in production) |
| Auth | bcrypt, JWT in httpOnly cookies, Google Identity Services |
| Agents | LangGraph, LangChain, Groq (`gpt-oss-20b` for routing, `gpt-oss-120b` for planning) |
| Places | Wikivoyage listings, OpenStreetMap Nominatim |
| RAG | pgvector + BM25; Jina AI embeddings + reranking in production, local fastembed + ChromaDB in development |
| Storage | Neon PostgreSQL in production (users, trips, chats, vectors); SQLite + Chroma locally |
| Hosting | Vercel (static React site + FastAPI function) |
| Exports | fpdf2 (PDF), iCalendar, Markdown |

---

## 📂 Project Structure

```text
TravelGenie/
├── backend/
│   ├── agents/        # supervisor, specialists, planner, plan schema, tools
│   ├── api/           # FastAPI app + account routes
│   ├── rag/           # ingestion, vector store, retrieval pipeline
│   ├── auth.py        # passwords, sessions, Google sign-in
│   ├── db.py          # users, settings, trips (PostgreSQL or SQLite)
│   ├── places.py      # Wikivoyage + OpenStreetMap
│   ├── export.py      # PDF / .ics / Markdown
│   ├── config.py
│   └── llm.py
├── api/index.py       # Vercel entry point for the FastAPI app
├── data/guides/       # curated destination guides (auto-indexed)
├── frontend/src/
│   ├── pages/         # login, dashboard, new trip, trip workspace, settings
│   └── components/    # app shell, chat, plan views (options, timeline, map, stays)
├── storage/           # databases, vector store, caches (created at runtime, git-ignored)
├── requirements.txt      # production dependencies (what Vercel installs)
├── requirements-dev.txt  # + local server, local databases and on-device models
├── vercel.json
└── .env.example
```

---

## 🚀 Getting Started

You need **Python 3.11+** and **Node.js 20+**.

### 1. Backend

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env              # then add your keys
uvicorn backend.api.main:app --reload --port 8000
```

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173** and create an account.

---

## ☁️ Deploy (Vercel + Neon + Jina, free, no card)

In production nothing is stored on a laptop: **Vercel** serves the React site and runs the FastAPI backend as a
Python function, all data (accounts, settings, trips, chats, knowledge base) lives in **Neon** PostgreSQL with
pgvector, and **Jina AI** provides the search embeddings and reranking.

### 1. Neon (database)
Create a project at [neon.tech](https://neon.tech), open **Connect** and copy the connection string
(`postgresql://…?sslmode=require`). TravelGenie creates its tables and enables `pgvector` on first use.

### 2. Jina AI (search models)
Get a free API key at [jina.ai](https://jina.ai) (it starts with `jina_`).

### 3. Vercel (hosting)
1. Sign up at [vercel.com](https://vercel.com) with GitHub, then **Add New → Project** and import this repository.
2. Leave the build settings as they are (`vercel.json` configures them).
3. Under **Environment Variables**, add:

| Name | Value |
|---|---|
| `DATABASE_URL` | the Neon connection string |
| `GROQ_API_KEY` | your Groq key |
| `JINA_API_KEY` | your Jina key |
| `SECRET_KEY` | a long random string: `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `OPENWEATHERMAP_API_KEY` | optional, live forecasts |
| `TAVILY_API_KEY` | optional, web search |
| `GOOGLE_CLIENT_ID` | optional, Google sign-in (add your Vercel URL to the OAuth client's JavaScript origins) |
| `CONTACT_EMAIL` | recommended, shown in the Privacy Policy for privacy requests and grievances |
| `DAILY_AI_LIMIT` | optional, AI requests per user per day (default 40) |

4. Click **Deploy**. Every later `git push` to `main` redeploys automatically.

### Notes
- The first request after a quiet period starts a new function instance (a few seconds).
- Vercel's free Hobby plan is for personal, non-commercial projects.
- Locally, leave `DATABASE_URL` and `JINA_API_KEY` empty to use files in `storage/` and on-device models.

---

## 🔑 Environment Variables

| Variable | Required | Purpose |
|---|---|---|
| `GROQ_API_KEY` | ✅ | LLM for all agents |
| `TAVILY_API_KEY` | optional | Web-search fallback for research |
| `OPENWEATHERMAP_API_KEY` | optional | Live forecasts |
| `GOOGLE_CLIENT_ID` | optional | Shows "Continue with Google" |
| `DATABASE_URL` | production | Neon / PostgreSQL connection string (local files are used when empty) |
| `JINA_API_KEY` | production | Jina AI embeddings + reranking (on-device models are used when empty) |
| `SECRET_KEY` | production | Signs login sessions (auto-generated locally if empty) |
| `COOKIE_SECURE` | optional | HTTPS-only cookies (on automatically on Vercel) |
| `GROQ_MODEL` / `GROQ_FAST_MODEL` / `GROQ_WRITER_MODEL` | optional | Override the models |

### Setting up Google sign-in

1. Open [Google Cloud Console → Credentials](https://console.cloud.google.com/apis/credentials) and create an **OAuth client ID** of type **Web application**.
2. Under **Authorised JavaScript origins**, add `http://localhost:5173` (and your production URL later).
3. Copy the Client ID into `GOOGLE_CLIENT_ID` in `.env` and restart the API. The Google button appears on the login page.

> **Groq free tier:** about 8,000 tokens per minute per model. A full three-option plan uses most of one minute's budget, so back-to-back plans may need a short wait. The app retries automatically.

---

## 🔌 API

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/auth/signup` · `/login` · `/google` · `/logout` · `/logout-all` | Accounts |
| `GET` | `/api/auth/me` | Current user + settings |
| `PUT` | `/api/account/profile` · `/api/account/password` · `/api/settings` | Profile, password, preferences |
| `DELETE` | `/api/account` | Delete account and all trips |
| `GET` | `/api/trips` · `/api/trips/{id}` | Your trips / one trip with its plan and chat |
| `PATCH` · `DELETE` | `/api/trips/{id}` | Rename, favourite, delete |
| `POST` | `/api/trips/{id}/select` | Choose an option: builds its detailed plan and focuses the chat on it |
| `GET` | `/api/trips/{id}/export?format=pdf\|ics\|md&option=budget\|luxury\|yours` | Download |
| `POST` | `/api/chat` | Run the agent team (SSE: `agent`, `token`, `final`, `error`) |
| `GET/POST/DELETE` | `/api/documents` | Knowledge base |
| `POST` | `/api/search` | Inspect the RAG pipeline |

Interactive docs are at http://localhost:8000/docs.

---

## 💡 Future Enhancements

- 🏨 Real hotel booking integration
- 👥 Collaborative / group trip planning
- 💸 Expense tracker during the trip
- 🌐 Multi-language support

---

## 🙏 Data

Stay and sightseeing listings come from [Wikivoyage](https://en.wikivoyage.org) (CC BY-SA). Maps and geocoding © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors.

---

⭐ If you found this project useful, consider giving it a star on GitHub!
