from langchain_ollama import ChatOllama, OllamaEmbeddings
from src.config import APP_SETTINGS

def create_chat_model(
    num_predict: int | None = None,
) -> ChatOllama:
    return ChatOllama(
        model=APP_SETTINGS.chat_model,
        temperature=0,
        num_predict=(
            num_predict
            if num_predict is not None
            else APP_SETTINGS.chat_num_predict
        ),
        num_ctx=APP_SETTINGS.chat_num_ctx,
        keep_alive=APP_SETTINGS.model_keep_alive,
    )


def create_embeddings() -> OllamaEmbeddings:
    return OllamaEmbeddings(model=APP_SETTINGS.embedding_model)
