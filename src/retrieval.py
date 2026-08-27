from pathlib import Path
from langchain_core.documents import Document
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from src.config import APP_SETTINGS
from src.llm import create_embeddings


class BVGRetriever:

    def __init__(self) -> None:
        self.vector_store = InMemoryVectorStore(
            embedding=create_embeddings()
        )

        self._build_index()

    def _build_index(self) -> None:
        documents = self._load_documents()

        if not documents:
            raise RuntimeError(
                f"No Markdown documents found in "
                f"{APP_SETTINGS.knowledge_dir}"
            )

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=APP_SETTINGS.chunk_size,
            chunk_overlap=APP_SETTINGS.chunk_overlap,
            separators=[
                "\n## ",
                "\n### ",
                "\n\n",
                "\n",
                ". ",
                " ",
            ],
        )

        chunks = splitter.split_documents(documents)

        self.vector_store.add_documents(chunks)

    def _load_documents(self) -> list[Document]:
        documents: list[Document] = []

        root = APP_SETTINGS.knowledge_dir

        for path in root.rglob("*.md"):
            relative_path = path.relative_to(root)

            # Example:
            # tickets/single_ticket.md -> category=tickets
            category = (
                relative_path.parts[0]
                if len(relative_path.parts) > 1
                else "general"
            )

            documents.append(
                Document(
                    page_content=path.read_text(encoding="utf-8"),
                    metadata={
                        "source": str(relative_path),
                        "filename": path.name,
                        "category": category,
                    },
                )
            )

        return documents

    def retrieve(
        self,
        query: str,
        k: int | None = None,
    ) -> list[tuple[Document, float]]:

        return self.vector_store.similarity_search_with_score(
            query=query,
            k=k or APP_SETTINGS.retrieval_k,
        )