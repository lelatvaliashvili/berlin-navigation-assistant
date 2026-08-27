from langchain_ollama import ChatOllama, OllamaEmbeddings
from src.config import APP_SETTINGS

def create_chat_model() -> ChatOllama:
    return ChatOllama(
        model=APP_SETTINGS.chat_model,
        temperature=0,
    )


def create_embeddings() -> OllamaEmbeddings:
    return OllamaEmbeddings(model=APP_SETTINGS.embedding_model)