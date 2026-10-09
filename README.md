# SunDesk Copilot

An agentic RAG support assistant for a rooftop solar company, built with **LangGraph, Groq, Pinecone, local embeddings, Tavily, FastAPI, Streamlit and LangSmith**.

It answers support questions from the company's private documents first, falls back to web search only when that evidence is weak, remembers each conversation, and shows the path it took for every answer.

The full walkthrough, with problem statement and demo script, is in [docs/SunDesk_Copilot_Project_Guide.pdf](docs/SunDesk_Copilot_Project_Guide.pdf).

---

## 1. Business Problem

### Customer

**Aravalli Solar Works**, a fictional rooftop solar company with four service regions. Every name, price, error code and policy in the sample knowledge base is invented.

### Problem

Service Desk agents and field engineers answer the same questions all day: what an error code means, whether a fault is under warranty, how long installation takes, why a bill has not dropped. The answers are spread across several internal documents.

- Keyword search returns whole documents instead of one clear answer.
- A plain chatbot answers confidently even without company information.
- Some questions, such as current subsidy amounts, are not in the private documents at all.
- Follow-up questions ("and for the battery?") need the earlier conversation.

### Goal

1. Search trusted private knowledge first.
2. Check whether the retrieved evidence is good enough.
3. Use web search only when private knowledge is insufficient.
4. Rewrite weak queries and retry once.
5. Keep conversation history so follow-ups work.
6. Show the decision path, and trace every run for debugging.
7. Let authorised staff add documents without editing code.

---

## 2. Features

| Feature | Details |
|---|---|
| Agentic workflow | Route, retrieve, grade, web fallback, rewrite and retry, grounded answer |
| Conversation memory | Chat threads saved as LangGraph checkpoints in SQLite |
| History-aware answers | Router, graders and answer steps read earlier turns; follow-ups get a rewritten search query |
| Streamlit chat UI | New chat, saved chat list, delete chat, source badge, sources and agent trace per answer |
| LangSmith observability | Every graph step and LLM call traced, grouped by chat thread |
| Document ingestion | Upload PDF, TXT, Markdown or DOCX from the UI or the API |
| REST API and basic web UI | FastAPI endpoints plus a single-page HTML UI |
| Audit log | One SQLite row per question with source and trace |

---

## 3. Architecture

```text
        Streamlit chat UI                 HTML/JS web UI
        (streamlit_app.py)                (templates/, static/)
               |                                 | POST /api/chat
               |                                 v
               |                              FastAPI
               |                                 |
               +---------------+-----------------+
                               v
                   LangGraph agentic workflow  ------> LangSmith traces
                     (app/rag/workflow.py)
                               |
        +-----------+----------+-----------+------------------+
        v           v                      v                  v
   Groq LLM    Pinecone private KB     Tavily web       SQLite checkpoints
               (local embeddings)       search          (chat threads)
```

## 4. Workflow

```text
Question (in a chat thread)
   |
[1] Route question
   |-- conversation / greeting ------------> Direct answer (uses chat history)
   |
   +-- support question
          |
[2] Follow-up search query (only when there are earlier turns)
          |
[3] Retrieve from private Pinecone KB  <---------------+
          |                                            |
[4] Grade private evidence                             |
     |            |                                    |
   GOOD         WEAK                                   |
     |            |                                    |
Answer from KB  [5] Tavily web search                  |
                  |                                    |
                [6] Grade web evidence                 |
                  |            |                       |
                GOOD         WEAK                      |
                  |            |                       |
          Answer from web   [7] Rewrite query (once) --+
                               |
                        Insufficient evidence
          |
[8] Save answer, sources and trace to the thread
```

---

## 5. Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| Agent workflow | LangGraph | Stateful routing and conditional decisions |
| LLM | Groq (`openai/gpt-oss-20b`) | Routing, grading, rewriting, answer generation |
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2` | Local 384-dimension embeddings, no API key |
| Vector DB | Pinecone | Private knowledge base |
| Web search | Tavily | Fallback when the private KB is insufficient |
| Chat memory | `langgraph-checkpoint-sqlite` | Thread checkpoints in `data/chat_checkpoints.db` |
| Observability | LangSmith | Run traces grouped by thread |
| Chat UI | Streamlit | Threaded chat interface |
| API | FastAPI | REST endpoints and basic web UI |
| Audit | SQLite | Decision-path log in `data/audit.db` |
| Packaging | Docker | Container for the FastAPI service |

---

## 6. Project Structure

```text
.
├── app/
│   ├── api/routes.py            # Chat, health and ingestion APIs
│   ├── core/config.py           # Settings, .env loading, LangSmith switch
│   ├── core/logging.py
│   ├── rag/state.py             # Graph state and structured decisions
│   ├── rag/vectorstore.py       # Local embeddings + Pinecone
│   ├── rag/workflow.py          # Agentic graph, checkpointer, thread helpers
│   ├── services/audit.py        # SQLite audit log
│   ├── services/ingestion.py    # PDF/TXT/MD/DOCX loading and chunking
│   └── main.py                  # FastAPI application
├── docs/
│   ├── knowledge_base/          # Six Aravalli Solar Works documents (ingested)
│   ├── SunDesk_Copilot_Project_Guide.md / .html / .pdf
│   ├── assets/                  # Diagrams (SVG) and guide.css
│   └── build_pdf.py             # Builds the PDF from the Markdown guide
├── static/, templates/          # Basic HTML/CSS/JS UI
├── data/                        # audit.db, chat_checkpoints.db (created at runtime)
├── uploads/                     # Files uploaded through the UI
├── streamlit_app.py             # Streamlit chat UI
├── ingest_sample_kb.py          # Loads docs/knowledge_base into Pinecone
├── run.py                       # Starts FastAPI on port 8080
├── requirements.txt
├── Dockerfile
└── .env.example
```

---

## 7. Setup

### Step 1: virtual environment

```bash
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # macOS/Linux
```

### Step 2: dependencies

```bash
pip install -r requirements.txt
```

The first run downloads the embedding model (about 90 MB).

### Step 3: environment

Copy `.env.example` to `.env` and fill in the keys.

| Variable | Description | Required |
|---|---|---|
| `GROQ_API_KEY` | Groq LLM key | Yes |
| `TAVILY_API_KEY` | Tavily web search key | Yes |
| `PINECONE_API_KEY` | Pinecone key | Yes |
| `LANGSMITH_API_KEY` | Turns LangSmith tracing on when present | No |
| `LANGSMITH_PROJECT` | LangSmith project name (default `sundesk-copilot`) | No |
| `ADMIN_API_KEY` | Password for document upload (default `change-me`) | No |
| `PINECONE_INDEX_NAME` | Index name (default `sundesk-solar-rag`) | No |
| `PINECONE_NAMESPACE` | Namespace (default `aravalli-solar-kb`) | No |
| `GROQ_MODEL` | Groq model (default `openai/gpt-oss-20b`) | No |
| `EMBEDDING_MODEL` | Embedding model (default `sentence-transformers/all-MiniLM-L6-v2`) | No |

Never commit `.env`. It is already listed in `.gitignore`.

### Step 4: load the knowledge base

```bash
python ingest_sample_kb.py
```

This creates the Pinecone index if needed and uploads the documents in `docs/knowledge_base/`. Run it once; running it again adds duplicate chunks.

### Step 5: run

| Interface | Command | Address |
|---|---|---|
| Streamlit chat UI (recommended) | `streamlit run streamlit_app.py` | http://localhost:8501 |
| FastAPI and basic web UI | `python run.py` | http://127.0.0.1:8080 |
| API docs | (served by FastAPI) | http://127.0.0.1:8080/docs |

---

## 8. Conversation Memory

Each chat has a `thread_id`. LangGraph saves the graph state after every step to `data/chat_checkpoints.db`, so chats survive a restart and can be reopened from the Streamlit sidebar.

Earlier turns are used in three ways:

- The router sees the history, so "what did you just say?" goes to a direct reply instead of a document search.
- For support questions, a follow-up such as "and for the battery?" becomes the search query "Battery warranty?".
- The graders and answer steps read the last 8 messages to understand what the question refers to. Facts still have to come from the evidence.

The basic web UI creates one thread per page load. API calls without a `thread_id` are answered statelessly.

## 9. Observability with LangSmith

Add `LANGSMITH_API_KEY` to `.env`. Tracing then switches on automatically and runs go to the `sundesk-copilot` project. Each run shows every graph step, the prompts, responses, timings and token use. Runs carry the chat's `thread_id`, so the Threads view groups a conversation together.

---

## 10. Demo Scenarios

| Scenario | Ask | Expected path |
|---|---|---|
| Private KB answer | What does error code AS-210 mean? | Router KB, KB grade GOOD, answer from private KB |
| Follow-up | What should I check first for it? | Follow-up search query names AS-210, answer from private KB |
| Web fallback | What is the current rooftop solar subsidy for homes in India? | KB grade WEAK, Tavily search, web grade GOOD, answer with a verification warning |
| Conversation recap | Can you summarise what you told me so far? | Router DIRECT, answered from chat history |
| Greeting | Hello! | Router DIRECT, no retrieval |

To add a document, open "Add company document" in the Streamlit sidebar, enter the admin key and upload a PDF, TXT, Markdown or DOCX file.

---

## 11. API Endpoints

### `GET /api/health`

Health check.

### `POST /api/chat`

```json
{
  "question": "How long is the inverter warranty?",
  "thread_id": "optional-thread-id"
}
```

Response:

```json
{
  "answer": "...",
  "source_used": "private_kb",
  "trace": ["Router → KB", "Private KB retrieval → 4 chunks", "KB evidence grade → GOOD", "Answer generation → PRIVATE KB"],
  "citations": [{"title": "04_warranty_and_service_policy.md", "url": "", "type": "private_kb"}],
  "rewritten_query": "..."
}
```

`source_used` is one of `private_kb`, `web_search`, `direct` or `insufficient_evidence`.

### `POST /api/ingest`

Protected by the `X-Admin-Key` header. Uploads a document and adds its chunks to Pinecone.

---

## 12. Documentation

The project guide is written in Markdown and built into a PDF:

```bash
python docs/build_pdf.py
```

Edit `docs/SunDesk_Copilot_Project_Guide.md` and rerun the command. It needs Edge or Chrome installed, because the page is printed to PDF by a headless browser.

- Diagrams are SVG files in `docs/assets/`; colours, tiles, callouts and tables are styled in `docs/assets/guide.css`.
- `<div class="pagebreak"></div>` on its own line starts a new page.
- An HTML copy is written next to the PDF and can be opened in a browser.
- Pass another Markdown file as an argument to build a PDF from it with the same styling.

## 13. Known Limitations

- Groq free-tier rate limits can slow answers; one question makes 3 to 9 LLM calls.
- The small Groq model occasionally adds a detail that is not in the documents.
- Retrieval is semantic only; there is no keyword search.
- Re-running ingestion duplicates chunks unless the Pinecone namespace is cleared first.
- The admin key is a single shared secret and there is no user login.
- The Dockerfile runs the FastAPI service only, not the Streamlit UI.

## 14. Origin

This project started from a tutorial template for an IT-support copilot built around a fictional company called NovaRetail. The domain, documents, prompts, memory, Streamlit UI and observability were rebuilt for this project; the original tutorial material is not part of this repository.
