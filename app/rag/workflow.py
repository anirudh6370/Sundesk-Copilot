import logging
import sqlite3
from typing import Literal
from langchain_core.messages import AIMessage, HumanMessage
from langchain_groq import ChatGroq
from langgraph.checkpoint.sqlite import SqliteSaver
from langchain_tavily import TavilySearch
from langgraph.graph import StateGraph, START, END
from app.core.config import get_settings
from app.rag.state import AgentState, RouteDecision, EvidenceGrade
from app.rag.vectorstore import get_retriever

logger = logging.getLogger(__name__)
settings = get_settings()

_llm = None
_web_search = None

def llm():
    global _llm
    if _llm is None:
        if not settings.groq_api_key:
            raise RuntimeError("GROQ_API_KEY is missing")
        _llm = ChatGroq(
            model=settings.groq_model,
            temperature=0,
            api_key=settings.groq_api_key,
            max_retries=5,
            timeout=60,
        )
    return _llm

def web_search_tool():
    global _web_search
    if _web_search is None:
        if not settings.tavily_api_key:
            raise RuntimeError("TAVILY_API_KEY is missing")
        _web_search = TavilySearch(
            tavily_api_key=settings.tavily_api_key,
            max_results=5,
            topic="general",
            include_answer=True,
            include_raw_content=False,
        )
    return _web_search

def add_trace(state: AgentState, message: str):
    return [*state.get("trace", []), message]

def history_text(state: AgentState, limit: int = 8, max_chars: int = 500) -> str:
    """Earlier turns of this thread (excluding the current message) as a transcript.
    Long answers are trimmed so the history does not crowd out the evidence or the token budget."""
    history = state["messages"][:-1][-limit:]
    if not history:
        return "(no earlier messages)"
    lines = []
    for m in history:
        text = m.content if len(m.content) <= max_chars else m.content[:max_chars] + "…"
        lines.append(f"{'User' if m.type == 'human' else 'Assistant'}: {text}")
    return "\n".join(lines)

def contextualize(state: AgentState):
    if len(state["messages"]) < 2:
        return {}
    # Only the search query is rewritten; the user's own words stay in state["question"]
    # and the later steps read the conversation history directly.
    query = llm().invoke(f"""
Write the search query for the new message in a rooftop solar support conversation.
If the message relies on earlier turns ("it", "that fault", "and for the battery?"), write a short
standalone question that names the thing being referred to (error code, component, plan or policy).
If the message already names its subject, return it unchanged. Do not answer, return only the query.
Conversation:\n{history_text(state)}
New message: {state['question']}
""").content.strip()
    if not query or query == state["question"]:
        return {}
    return {"current_query": query, "trace": add_trace(state, f"Follow-up search query → {query}")}

def route_question(state: AgentState):
    router = llm().with_structured_output(RouteDecision, method="json_schema")
    decision = router.invoke(f"""
You route messages for a rooftop solar company's support assistant.
Use kb for questions about solar installation, commissioning, inverters, error codes, monitoring,
warranty, maintenance, safety, net metering, billing, subsidies, or company policies and services.
Use direct for anything that needs no company knowledge lookup:
- greetings, thanks and casual chat
- messages where the user only introduces themselves or describes their own setup without asking anything
- questions about the user or the conversation itself (their name, what they said earlier,
  a recap, summary or rephrasing of previous answers)
Conversation so far:\n{history_text(state)}
Question: {state['question']}
Return valid JSON like {{"route":"kb"}}.
""")
    return {"source_used": decision.route, "trace": add_trace(state, f"Router → {decision.route.upper()}")}

def route_after_router(state: AgentState) -> Literal["contextualize", "direct_answer"]:
    return "contextualize" if state["source_used"] == "kb" else "direct_answer"

def retrieve_kb(state: AgentState):
    docs = get_retriever().invoke(state["current_query"])
    return {"kb_docs": docs, "trace": add_trace(state, f"Private KB retrieval → {len(docs)} chunks")}

def grade_kb(state: AgentState):
    grader = llm().with_structured_output(EvidenceGrade, method="json_schema")
    context = "\n\n".join(f"Source: {d.metadata.get('source','unknown')}\n{d.page_content}" for d in state["kb_docs"])
    grade = grader.invoke(f"""
You grade evidence for a rooftop solar company's support assistant.
Use the conversation so far only to understand what the question refers to.
Conversation so far:\n{history_text(state)}
Question: {state['question']}
Private company KB evidence:\n{context}
Return good only if the evidence is sufficient to answer confidently and specifically.
Otherwise return weak. JSON: {{"grade":"good"}} or {{"grade":"weak"}}.
""")
    return {"kb_grade": grade.grade, "trace": add_trace(state, f"KB evidence grade → {grade.grade.upper()}")}

def after_kb(state: AgentState) -> Literal["generate_from_kb", "search_web"]:
    return "generate_from_kb" if state["kb_grade"] == "good" else "search_web"

def search_web(state: AgentState):
    result = web_search_tool().invoke({"query": state["current_query"]})
    lines, citations = [], []
    if isinstance(result, dict):
        if result.get("answer"):
            lines.append("Search answer: " + result["answer"])
        for item in result.get("results", []):
            title, url, content = item.get("title", ""), item.get("url", ""), item.get("content", "")
            lines.append(f"Title: {title}\nURL: {url}\nContent: {content}")
            citations.append({"title": title or url, "url": url, "type": "web"})
    else:
        lines.append(str(result))
    return {
        "web_results": "\n\n".join(lines),
        "citations": citations,
        "source_used": "web",
        "trace": add_trace(state, "Web fallback → Tavily search"),
    }

def grade_web(state: AgentState):
    grader = llm().with_structured_output(EvidenceGrade, method="json_schema")
    grade = grader.invoke(f"""
Use the conversation so far only to understand what the question refers to.
Conversation so far:\n{history_text(state)}
Question: {state['question']}
Web evidence:\n{state['web_results']}
Return good if the evidence is sufficient and directly relevant; otherwise weak.
Return valid JSON like {{"grade":"good"}}.
""")
    return {"web_grade": grade.grade, "trace": add_trace(state, f"Web evidence grade → {grade.grade.upper()}")}

def after_web(state: AgentState) -> Literal["generate_from_web", "rewrite_query", "insufficient"]:
    if state["web_grade"] == "good":
        return "generate_from_web"
    if state["retry_count"] < settings.max_retries:
        return "rewrite_query"
    return "insufficient"

def rewrite_query(state: AgentState):
    rewritten = llm().invoke(f"""
Rewrite this rooftop solar support question for better private knowledge retrieval and public web search.
Preserve intent, add useful technical keywords, do not answer, return only the query.
Question: {state['current_query']}
""").content.strip()
    return {
        "current_query": rewritten,
        "retry_count": state["retry_count"] + 1,
        "trace": add_trace(state, f"Query rewrite → {rewritten}"),
    }

def generate_from_kb(state: AgentState):
    context = "\n\n".join(f"[Source: {d.metadata.get('source','unknown')}]\n{d.page_content}" for d in state["kb_docs"])
    answer = llm().invoke(f"""
You are a rooftop solar support copilot. Answer ONLY from the private company KB below.
Be concise, actionable, and safe. If steps are present, present them clearly.
Do not invent policy details. Mention that the answer is based on the company's private knowledge base.
Use the conversation so far only to understand what the user means and their situation; facts must come from the KB.
Conversation so far:\n{history_text(state)}\n
Question: {state['question']}\n\nPrivate KB:\n{context}
""").content
    citations = []
    seen = set()
    for d in state["kb_docs"]:
        src = d.metadata.get("source", "Private KB")
        if src not in seen:
            seen.add(src)
            citations.append({"title": src.replace("\\", "/").split("/")[-1], "url": "", "type": "private_kb"})
    return {"answer": answer, "source_used": "private_kb", "citations": citations, "trace": add_trace(state, "Answer generation → PRIVATE KB")}

def generate_from_web(state: AgentState):
    answer = llm().invoke(f"""
You are a rooftop solar support copilot. The private company KB was insufficient.
Answer ONLY from the web evidence below. Clearly say this is external web information and should be verified against the official source before it is quoted to a customer.
Use the conversation so far only to understand what the user means and their situation; facts must come from the web evidence.
Conversation so far:\n{history_text(state)}\n
Question: {state['question']}\n\nWeb evidence:\n{state['web_results']}
""").content
    return {"answer": answer, "source_used": "web_search", "trace": add_trace(state, "Answer generation → WEB SEARCH")}

def direct_answer(state: AgentState):
    answer = llm().invoke(f"""
You are a rooftop solar support copilot. Respond briefly and naturally to the user's message.
If it refers to the conversation so far, answer from that conversation. Do not invent company facts.
Conversation so far:\n{history_text(state)}\n
Message: {state['question']}
""").content
    return {"answer": answer, "source_used": "direct", "trace": add_trace(state, "Direct response → no retrieval")}

def insufficient(state: AgentState):
    return {
        "answer": "I couldn't find enough reliable evidence in the company knowledge base or external search to answer confidently. Please contact the Service Desk or provide more details.",
        "source_used": "insufficient_evidence",
        "trace": add_trace(state, "Stopped → insufficient reliable evidence"),
    }

def finalize(state: AgentState):
    meta = {"source_used": state["source_used"], "trace": state["trace"], "citations": state["citations"]}
    return {"messages": [AIMessage(content=state["answer"], additional_kwargs=meta)]}

def build_graph(checkpointer=None):
    graph = StateGraph(AgentState)
    for name, fn in {
        "contextualize": contextualize,
        "finalize": finalize,
        "route_question": route_question,
        "retrieve_kb": retrieve_kb,
        "grade_kb": grade_kb,
        "search_web": search_web,
        "grade_web": grade_web,
        "rewrite_query": rewrite_query,
        "generate_from_kb": generate_from_kb,
        "generate_from_web": generate_from_web,
        "direct_answer": direct_answer,
        "insufficient": insufficient,
    }.items():
        graph.add_node(name, fn)

    graph.add_edge(START, "route_question")
    graph.add_edge("contextualize", "retrieve_kb")
    graph.add_conditional_edges("route_question", route_after_router, {
        "contextualize": "contextualize", "direct_answer": "direct_answer"
    })
    graph.add_edge("retrieve_kb", "grade_kb")
    graph.add_conditional_edges("grade_kb", after_kb, {
        "generate_from_kb": "generate_from_kb", "search_web": "search_web"
    })
    graph.add_edge("search_web", "grade_web")
    graph.add_conditional_edges("grade_web", after_web, {
        "generate_from_web": "generate_from_web", "rewrite_query": "rewrite_query", "insufficient": "insufficient"
    })
    graph.add_edge("rewrite_query", "retrieve_kb")
    graph.add_edge("generate_from_kb", "finalize")
    graph.add_edge("generate_from_web", "finalize")
    graph.add_edge("direct_answer", "finalize")
    graph.add_edge("insufficient", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile(checkpointer=checkpointer)

# Chats are checkpointed per thread_id in SQLite; check_same_thread=False because
# FastAPI and Streamlit call the graph from worker threads.
checkpointer = SqliteSaver(sqlite3.connect(settings.checkpoint_db_path, check_same_thread=False))
checkpointer.setup()

agent_graph = build_graph(checkpointer)
stateless_graph = build_graph()

def thread_config(thread_id: str):
    return {"configurable": {"thread_id": thread_id}, "metadata": {"thread_id": thread_id}}

def list_threads() -> list[dict]:
    """Saved chat threads, most recently active first, titled by their first question."""
    rows = checkpointer.conn.execute(
        "SELECT thread_id FROM checkpoints GROUP BY thread_id ORDER BY MAX(checkpoint_id) DESC"
    ).fetchall()
    threads = []
    for (thread_id,) in rows:
        messages = get_messages(thread_id)
        if messages:
            threads.append({"thread_id": thread_id, "title": messages[0].content})
    return threads

def get_messages(thread_id: str) -> list:
    return agent_graph.get_state(thread_config(thread_id)).values.get("messages", [])

def delete_thread(thread_id: str) -> None:
    checkpointer.delete_thread(thread_id)

def ask(question: str, thread_id: str | None = None):
    """Run one turn. With a thread_id the turn is checkpointed and can use earlier turns."""
    initial: AgentState = {
        "messages": [HumanMessage(content=question)],
        "question": question,
        "current_query": question,
        "kb_docs": [],
        "web_results": "",
        "kb_grade": "",
        "web_grade": "",
        "answer": "",
        "source_used": "",
        "retry_count": 0,
        "trace": [],
        "citations": [],
    }
    if thread_id:
        return agent_graph.invoke(initial, thread_config(thread_id))
    return stateless_graph.invoke(initial)
