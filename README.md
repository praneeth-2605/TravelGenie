# 🌍 TravelGenie — Multi-Agent AI Travel Planner

Tell TravelGenie where you're going and for how long. A team of AI agents finds **real hostels, hotels, sights and restaurants**, checks the weather, researches the destination, and builds **three complete trip options** with an **hour-by-hour itinerary**: where you arrive (airport, station or bus stand), real travel distance and time for every leg, check-in, every visit and meal, and the way back to your hotel:

| | Option | What you get |
|---|---|---|
| 💰 | **Budget** | The cheapest sensible trip: hostels, street food, public transport |
| 💎 | **Luxury** | Premium comfort: top hotels, fine dining, private transfers |
| 🎯 | **Your budget** | Fitted to *your* budget range |

Each option recommends an area and type of stay and offers **up to six real hotels with photos**. You choose one and the itinerary is re-timed around it (until you do, it just says “your hotel in <area>”).

**Choose a plan** and TravelGenie adds a booking checklist, money tips and what's good to know, and the chat switches to discussing *your* plan. Questions are just answered; the agents only re-plan when you ask for a change.

After every request you get separate sections: **Overview, Getting there (flight / train / bus / car / ferry), Hotels, Itinerary, Weather, Web search and Map**, and you can export to **PDF, calendar (.ics) or Markdown**.

---

## ✨ Features

- 👤 **Accounts**: email + password sign-up, "Continue with Google", secure httpOnly sessions, log out everywhere, account deletion
- 📱 **Installable app**: add TravelGenie to your phone's home screen; saved trips open offline
- 🔗 **Share trips**: public read-only links and one-tap WhatsApp sharing (chats are never shared)
- 🎫 **Booking links**: Google Flights, IRCTC, redBus, Booking.com and Google Maps, pre-filled from the plan
- ₹ **Made for India**: Indian number formats (₹1,50,000) and per-person or total budgets
- ⚖️ **Fair use and compliance**: daily AI request limits, Privacy Policy and Terms (DPDP Act 2023), consent at sign-up, one-click data download
- 🔒 **Privacy**: deleting a trip or an account also deletes its chat history
- ⚙️ **User settings**: home city, home currency, usual travellers, typical budget range, travel style, pace, interests, dietary needs, light/dark theme. These are used as defaults for every plan.
- 📊 **Dashboard**: your trips with prices for all three options, stats, upcoming-trip countdown, favourites
- 🕒 **Hour-by-hour itinerary**: real road distances and travel times (OpenStreetMap routing), realistic meal times, opening hours respected, arrival and departure hubs named
- 🏨 **Choose your hotel**: several real hotels per option with photos; the plan follows your choice
- 📷 **Real photos** of sights, restaurants and stays (Wikimedia Commons, credited; “area photo” when it shows the surroundings)
- ✅ **Only real places**: every named stop must be a real listing; anything else is made generic or flagged “not verified”
- 🎯 **Choose a plan** → booking checklist, money tips + chat focused on it
- ↔️ **Resizable chat panel** (drag the divider; remembered on your device)
- 🚆 **Every way to get there**: flights, trains, buses, self-drive, taxi and ferries compared by price, time, route and where to book
- 🧩 **Separate sections** after each request: Overview, Getting there, Hotels, Itinerary, Weather, Web search, Map
- 🤖 **Nine specialised agents** coordinated by a supervisor (LangGraph), running in parallel
- 🏨 **Real places**: stays (by price tier, with listed prices), sights and restaurants from Wikivoyage, plus geocoding from OpenStreetMap
- 🗺️ **Interactive map** with day-coloured pins and your stay
- 📚 **Advanced RAG** over curated travel guides: hybrid search, multi-query, reranking, citations, web fallback
- 🔁 **Conversational refinement**: "make it cheaper", "add a beach day", "make the luxury option more special"
- 📄 **Exports**: PDF (one option or all three), calendar file for Google/Apple/Outlook, Markdown

---

## 🧠 The agent team

```text
                       ┌──► Research   (RAG over travel guides + web)  ──┐
                       ├──► Weather    (live forecast / seasonal)        ─┤
  you ─► Supervisor ───┼──► Stays      (hostels & hotels by price tier)  ─┼─► Planner ─► Scheduler ─► 3 options + timed days
                       ├──► Sightseeing (local sights & activities)      ─┤
                       ├──► Transport  (flight/train/bus/car/ferry)      ─┤
                       ├──► Web search (what to know before you go)      ─┤
                       └──► Booking    (simulated bookings)              ──┘   Writer ─► cited answers
```

| Agent | Job |
|---|---|
| **Supervisor** | Understands the request, fills gaps from your settings, decides the intent (plan / revise / question / book / chat) and which agents to call |
| **Research** | Hybrid RAG over curated guides and cached web results |
| **Weather** | Live 5-day forecast, or seasonal norms when the trip is further out |
| **Stays** | Real places to stay from Wikivoyage, grouped Budget / Mid-range / Luxury with listed prices |
| **Sightseeing** | Real sights, activities and restaurants with coordinates and opening hours, matched to your interests |
| **Transport** | Compares every way to get there from your city (flight, train, bus, car, ferry): price range, duration, route, where to book |
| **Web search** | Live web results (Tavily), or the destination's Wikivoyage guide: safety, getting around, money, etiquette |
| **Planner** | Builds the three options (travel mode, arrival hub, costs, stay area and hotel shortlist, highlights) and picks and orders real places for each day, by id only; checks "Your budget" really fits your range |
| **Scheduler** (code) | Turns the ordered stops into a timed plan with real travel legs, meal times and opening hours, per option and per chosen hotel. No AI call, so choosing a hotel is instant |
| **Concierge** | When you choose an option: booking checklist, money tips and what's good to know |
| **Writer** | Answers questions with inline citations |

All the output formats (cards, timeline, map, PDF, calendar, Markdown) are generated from the one structured plan.

### 🧩 Pipeline and skills

Agents decide **what** to do (with an LLM); **skills** do one concrete job against real data, with caching and fallbacks
(`backend/skills/`, listed live at `/api/health`):

| Skill | Does | Source |
|---|---|---|
| `geocode` | Place name → coordinates | OpenStreetMap Nominatim |
| `find_places` | Stays, sights and restaurants | Wikivoyage listings |
| `find_photos` | Real, credited photos of places | Wikidata · Wikipedia · Wikimedia Commons |
| `area_photo` | Photo of a hotel's surroundings when it has none of its own | Wikimedia Commons |
| `route_legs` | Road distance and travel time between stops | OSRM (OpenStreetMap routing) |
| `build_schedule` | Timestamped day plan from ordered stops | TravelGenie code over the skills above |

```text
request ─► supervisor (intent + brief) ─► specialists in parallel ─► planner (LLM: options + ordered real place ids)
        ─► enrich: validate ids · photos · hotel shortlist ─► scheduler (code: times + legs) ─► plan
choose hotel ─► scheduler only (no AI)        question ─► writer (no re-plan)
```

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
│   ├── skills/        # geocode, places, photos, routing, scheduler (deterministic, cached)
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
Python function, all data (accounts, settings, trips, chats, guide search index) lives in **Neon** PostgreSQL with
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
| `POST` | `/api/trips/{id}/select` | Choose an option: builds its checklist and focuses the chat on it |
| `POST` | `/api/trips/{id}/hotel` | Pick (or clear) the hotel for an option; re-times its itinerary |
| `POST` · `DELETE` | `/api/trips/{id}/share` | Create or revoke a public share link |
| `GET` | `/api/trips/{id}/export?format=pdf\|ics\|md&option=budget\|luxury\|yours` | Download |
| `POST` | `/api/chat` | Run the agent team (SSE: `agent`, `token`, `final`, `error`) |

Interactive docs are at http://localhost:8000/docs.

---

## 💡 Future Enhancements

- 🏨 Real hotel booking integration
- 👥 Collaborative / group trip planning
- 💸 Expense tracker during the trip
- 🌐 Multi-language support

---

## 🙏 Data

Stay, sightseeing and restaurant listings come from [Wikivoyage](https://en.wikivoyage.org) (CC BY-SA). Photos from [Wikimedia Commons](https://commons.wikimedia.org) (credited per photo). Maps, geocoding and routing © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors, routing by [OSRM](https://project-osrm.org).

---

⭐ If you found this project useful, consider giving it a star on GitHub!
