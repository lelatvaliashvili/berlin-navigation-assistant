from dataclasses import dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent

#neutral system prompt
ASSISTANT_SYSTEM_PROMPT = (
    "You are a helpful conversational assistant focused on Berlin public "
    "transport. Use the provided context when it is available to answer "
    "questions about tickets, fares, travel rules, accessibility, and "
    "services. Answer naturally and concisely, and be accurate, welcoming, "
    "and friendly."
)

#clarification settings preconfigured
DEPARTURE_STATION_PROMPT = (
    "Which station would you like departure information for?"
)

JOURNEY_ENDPOINTS_PROMPT = (
    "Please provide an origin and destination to plan the journey."
)


@dataclass(frozen=True)
class AppSettings:
    chat_model: str = "llama3.1:8b"
    embedding_model: str = "nomic-embed-text"
    chat_num_predict: int = 256
    router_num_predict: int = 256
    chat_num_ctx: int = 4096
    model_keep_alive: str = "30m"
    history_message_limit: int = 6
    knowledge_dir: Path = ROOT_DIR / "knowledge" / "domain"
    chunk_size: int = 800
    chunk_overlap: int = 100
    retrieval_k: int = 3


@dataclass(frozen=True)
class TransitousSettings:
    base_url: str = "https://api.transitous.org"
    timeout_seconds: float = 15.0

    user_agent: str = "berlin-navigation-assistant/v0.1"

    departures_count: int = 5
    journey_result_count: int = 3


APP_SETTINGS = AppSettings()
TRANSITOUS_SETTINGS = TransitousSettings()
