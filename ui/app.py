import sys
from pathlib import Path

import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.chatbot import BVGAssistant


st.title("Berlin Navigation Assistant")

if "assistant" not in st.session_state:
    st.session_state.assistant = BVGAssistant(
        enable_completeness_guard=True
    )

if "messages" not in st.session_state:
    st.session_state.messages = []

if st.button("Reset conversation"):
    st.session_state.assistant.reset_session()
    st.session_state.messages = []
    st.rerun()

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.write(message["content"])

if prompt := st.chat_input("Ask about Berlin public transport"):
    st.session_state.messages.append(
        {"role": "user", "content": prompt}
    )
    with st.chat_message("user"):
        st.write(prompt)

    with st.chat_message("assistant"):
        try:
            with st.spinner("Thinking..."):
                response = st.session_state.assistant.ask(prompt)
            answer = response.answer
        except Exception as exc:
            answer = f"Error: {exc}"

        st.write(answer)

    st.session_state.messages.append(
        {"role": "assistant", "content": answer}
    )
