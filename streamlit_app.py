import os
import uuid
from pathlib import Path

import streamlit as st

from app.core.config import get_settings
from app.rag.vectorstore import add_documents
from app.rag.workflow import ask, delete_thread, get_messages, list_threads
from app.services.audit import init_db, write_audit
from app.services.ingestion import SUPPORTED, chunk_documents, load_file

settings = get_settings()
init_db()

SOURCE_LABELS = {
    "private_kb": ("Private knowledge base", "green"),
    "web_search": ("Web search", "orange"),
    "direct": ("Direct reply", "blue"),
    "insufficient_evidence": ("Insufficient evidence", "red"),
}
EXAMPLES = [
    "What does error code AS-210 mean?",
    "How long is the inverter warranty?",
    "What is the current rooftop solar subsidy for homes in India?",
]

st.set_page_config(page_title=settings.app_name, page_icon="☀️", layout="wide")

if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())


def new_chat():
    st.session_state.thread_id = str(uuid.uuid4())


def open_chat(thread_id: str):
    st.session_state.thread_id = thread_id


def remove_chat(thread_id: str):
    delete_thread(thread_id)
    if st.session_state.thread_id == thread_id:
        new_chat()


def render_answer_details(meta: dict):
    label, color = SOURCE_LABELS.get(meta.get("source_used", ""), (meta.get("source_used", ""), "gray"))
    if label:
        st.badge(label, color=color)
    citations = meta.get("citations") or []
    if citations:
        with st.expander(f"Sources ({len(citations)})"):
            for c in citations:
                st.markdown(f"- [{c['title']}]({c['url']})" if c.get("url") else f"- {c['title']}")
    trace = meta.get("trace") or []
    if trace:
        with st.expander("Agent trace"):
            for i, step in enumerate(trace, 1):
                st.markdown(f"{i}. {step}")


with st.sidebar:
    st.title(f"☀️ {settings.app_name}")
    st.caption("Private company knowledge first. Web search only when the evidence is weak.")
    st.button("＋ New chat", on_click=new_chat, use_container_width=True, type="primary")

    st.subheader("Chats")
    threads = list_threads()
    if not threads:
        st.caption("No saved chats yet.")
    for t in threads:
        title = t["title"] if len(t["title"]) <= 38 else t["title"][:38] + "…"
        is_current = t["thread_id"] == st.session_state.thread_id
        open_col, delete_col = st.columns([5, 1])
        open_col.button(
            title,
            key=f"open-{t['thread_id']}",
            on_click=open_chat,
            args=(t["thread_id"],),
            use_container_width=True,
            type="secondary" if not is_current else "primary",
        )
        delete_col.button("✕", key=f"del-{t['thread_id']}", on_click=remove_chat, args=(t["thread_id"],), help="Delete chat")

    st.divider()
    with st.expander("Add company document"):
        admin_key = st.text_input("Admin key", type="password")
        upload = st.file_uploader("PDF, TXT, Markdown or DOCX", type=[s.lstrip(".") for s in sorted(SUPPORTED)])
        if st.button("Index document", disabled=upload is None):
            if admin_key != settings.admin_api_key:
                st.error("Invalid admin key")
            else:
                upload_dir = Path(settings.upload_dir)
                upload_dir.mkdir(parents=True, exist_ok=True)
                dest = upload_dir / Path(upload.name).name
                dest.write_bytes(upload.getvalue())
                with st.spinner("Chunking, embedding and indexing..."):
                    chunks = chunk_documents(load_file(dest))
                    add_documents(chunks)
                st.success(f"Indexed {dest.name}: {len(chunks)} chunks")

    if os.getenv("LANGSMITH_TRACING", "").lower() == "true":
        st.caption(f"LangSmith tracing on · project `{os.getenv('LANGSMITH_PROJECT')}`")
    else:
        st.caption("LangSmith tracing off")


messages = get_messages(st.session_state.thread_id)
question = st.chat_input("Ask a solar support question...")

if not messages and not question:
    st.header("How can I help with solar support?")
    st.caption("Answers come from the Aravalli Solar Works knowledge base, with web search as a fallback.")
    for col, example in zip(st.columns(len(EXAMPLES)), EXAMPLES):
        if col.button(example, use_container_width=True):
            question = example

for m in messages:
    if m.type == "human":
        st.chat_message("user").write(m.content)
    else:
        with st.chat_message("assistant"):
            st.markdown(m.content)
            render_answer_details(m.additional_kwargs)

if question:
    st.chat_message("user").write(question)
    with st.chat_message("assistant"):
        try:
            with st.spinner("Running the agent workflow..."):
                result = ask(question, st.session_state.thread_id)
        except Exception as exc:
            st.error(f"Request failed: {exc}")
            st.stop()
        write_audit(question, result["source_used"], result.get("trace", []))
    # Rerun so the turn is drawn from the checkpoint and the sidebar picks up a new chat
    st.rerun()
