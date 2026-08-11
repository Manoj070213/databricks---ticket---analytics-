# Agentic Support-Ticket Analytics — Lakehouse + LLM + RAG

An end-to-end system that ingests customer support tickets into a Databricks
lakehouse, auto-tags each ticket with an LLM, aggregates the results into
analytics-ready tables, and serves everything through a secured FastAPI service
with a Retrieval-Augmented Generation (RAG) question-answering endpoint.

The pipeline mirrors how a real support organization would turn a raw stream of
tickets into decision-ready intelligence — categorised, prioritised, and
queryable in natural language.

---

## What it does

- **Ingests 8,000+ support tickets** into a Bronze → Silver → Gold medallion
  architecture on Delta Lake, using Apache Spark.
- **Auto-tags every ticket** by category, urgency, and sentiment into strict
  JSON using a Databricks-hosted LLM (schema-locked prompt + robust parser,
  100% JSON parse success across the dataset).
- **Aggregates** the tagged data into Gold analytics tables (category summary,
  daily volume by urgency, and a category × urgency priority matrix).
- **Orchestrates** the four pipeline stages as a scheduled Databricks Job — a
  four-task DAG that runs Bronze → Silver → Tagging → Gold end to end.
- **Serves** the results through a FastAPI REST API with API-key authentication,
  analytics endpoints, and a **RAG-style Q&A endpoint** that retrieves relevant
  tickets and answers questions with a large language model (Google Gemini),
  citing the source tickets it used.
- **Logs** every request with structured, timed observability output.

---

## Architecture

```
                 ┌──────────────── Databricks Lakehouse ────────────────┐
                 │                                                        │
  Raw tickets ──▶│  Bronze  ──▶  Silver  ──▶  LLM Tagging  ──▶  Gold      │
                 │  (raw)       (cleaned)    (JSON tags)     (aggregates) │
                 │      orchestrated as a scheduled Databricks Job        │
                 └────────────────────────────┬───────────────────────────┘
                                               │  export
                                               ▼
                 ┌──────────────── FastAPI Service (local) ─────────────┐
                 │  API-key auth  ·  analytics endpoints  ·  /ask (RAG)  │
                 │  retrieval → Gemini generation → grounded answer      │
                 │  structured request logging / observability          │
                 └───────────────────────────────────────────────────────┘
```

---

## Tech stack

| Layer | Technology |
|---|---|
| **Lakehouse** | Databricks, Delta Lake, Apache Spark (PySpark) |
| **Orchestration** | Databricks Jobs (scheduled 4-task DAG) |
| **LLM tagging** | Databricks-hosted foundation model (Llama 3.1 8B via `ai_query`) |
| **API** | FastAPI, Uvicorn, Pydantic |
| **RAG generation** | Google Gemini (`google-genai` SDK) |
| **Data handling** | pandas |
| **Auth & config** | API-key header auth, `python-dotenv` |
| **Observability** | Python `logging` (console + file) |

---

## Repository contents

| File | Description |
|---|---|
| `main.py` | FastAPI application: analytics endpoints, API-key auth, RAG `/ask` endpoint, and request logging |
| `tagged_export.csv` | The LLM-tagged ticket dataset exported from the Gold layer, served by the API |
| `.gitignore` | Excludes secrets (`.env`), the virtual environment, and caches |
| `api.log` | Runtime request log (regenerated on each run) |

The Databricks notebooks (`01_bronze_ingestion`, `02_silver_cleaning`,
`03_llm_tagging`, `04_gold_aggregates`) run inside the Databricks workspace and
produce the tagged dataset the API serves.

---

## API endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/` | — | Service status + ticket count |
| GET | `/health` | — | Health check |
| GET | `/stats/categories` | ✅ | Ticket counts by category |
| GET | `/stats/urgency` | ✅ | Ticket counts by urgency |
| GET | `/stats/sentiment` | ✅ | Ticket counts by sentiment |
| GET | `/tickets/{ticket_id}` | ✅ | Look up a single ticket |
| GET | `/tickets` | ✅ | Search tickets by keyword / category |
| POST | `/ask` | ✅ | RAG Q&A — retrieves relevant tickets and answers with an LLM, returning source ticket IDs |

Protected endpoints require an `X-API-Key` header.

---

## Running the API locally

**1. Clone and enter the project**
```bash
git clone <your-repo-url>
cd <project-folder>
```

**2. Create and activate a virtual environment**
```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate
```

**3. Install dependencies**
```bash
pip install fastapi uvicorn pandas python-dotenv google-genai
```

**4. Add your Gemini API key**

Create a file named `.env` in the project root:
```
GEMINI_API_KEY=your-gemini-api-key-here
```
Get a free key at https://aistudio.google.com/apikey. The `.env` file is
git-ignored, so the key stays on your machine.

**5. Start the server**
```bash
uvicorn main:app --reload
```

**6. Open the interactive docs**

Visit http://127.0.0.1:8000/docs for the auto-generated Swagger UI.

---

## Example: asking a question (RAG)

```bash
curl -X POST http://127.0.0.1:8000/ask \
  -H "X-API-Key: <your-api-key>" \
  -H "Content-Type: application/json" \
  -d '{"question": "What problems do customers have with refunds?"}'
```

Response:
```json
{
  "question": "What problems do customers have with refunds?",
  "answer": "Customers report wanting to cancel plans and receive refunds, with...",
  "sources": ["TK-102460", "TK-102428", "TK-107985", "..."]
}
```

The endpoint **retrieves** the most relevant tickets, **augments** the prompt
with them, and asks the LLM to answer **only** from that context — returning the
source ticket IDs so every answer is traceable.

---

## Design notes & honest limitations

- **Category tagging is strong and well-distributed** across all six classes.
  Urgency tagging skews toward "high" — a known limitation of the smaller
  tagging model — which was partially corrected through prompt engineering and
  could be improved further by upgrading to a larger model endpoint.
- **RAG retrieval is keyword-based** in this version. It works well when the
  question shares vocabulary with the tickets, but can miss semantically related
  tickets that use different words. The natural next step is **embedding-based
  retrieval** for semantic matching.
- **The ticket data is synthetic**, generated deterministically. The pipeline
  itself is identical to what a production system would run.

---

## Possible extensions

- Swap keyword retrieval for vector/embedding search (semantic RAG).
- Upgrade the tagging model for higher urgency/sentiment accuracy.
- Add a dashboard (Power BI / Streamlit) on top of the Gold tables.
- Connect the API directly to the live Delta tables instead of a CSV export.
