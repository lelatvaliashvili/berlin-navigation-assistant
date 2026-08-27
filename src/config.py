from dataclasses import dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent

@dataclass(frozen=True)
class AppSettings:
    chat_model: str = "llama3.1:8b"
    embedding_model: str = "nomic-embed-text"
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
