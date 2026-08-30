# berlin-navigation-assistant


# Setup

The application uses a local Ollama runtime. It requires Python 3.12 (the
project was tested with Python 3.12.x). 

Install Ollama separately, then install
the Python dependencies and pull the two models used by the assistant:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
ollama serve
ollama pull llama3.1:8b
ollama pull nomic-embed-text
```

The demo notebook is available at `notebooks/demo_usage.ipynb`. It runs real
baseline and fully guarded chatbot calls for a few representative prompts and
shows the answers and triggered guardrails side by side.

The Streamlit app is an optional, customer-facing conversational window. It
shows the polished assistant response without exposing guardrail traces.

Demo and results notebooks are to be inspected for details regarding the baseline or guarded path and which safeguards were activated.

Run the Streamlit application with:
```bash
streamlit run ui/app.py
```

For evaluation, run the automated checks with:

```bash
pytest -q
python -m evaluation.run_benchmark --judge
python -m evaluation.run_conversation_benchmark --judge
```

The evaluation commands make Ollama calls and record results under
`evaluation/results/`. The live journey/departure examples additionally need
network access to the Transitous API. Final reports use stable filenames and
are overwritten by a subsequent run, so copy a report to the archive if you
want to preserve it before rerunning.


# Tools and Libraries

- **LangChain / `langchain-ollama`**: connects the application to Ollama and
  provides message, document, text-splitting, and in-memory vector-store
  abstractions.
- **Ollama**: runs the local `llama3.1:8b` chat model and `nomic-embed-text`
  embedding model without an external API key.
- **Pydantic**: validates structured model output. Router and guardrail
  decisions must match typed schemas instead of being accepted as arbitrary
  JSON.
- **PyYAML**: loads the reviewed completeness and groundedness policies.
- **httpx**: calls the Transitous live-data API.
- **Streamlit**: provides the interactive demonstration UI.
- **Pytest**: runs unit and integration tests.
- **Pandas**: supports evaluation and notebook analysis.


# Knowledge 

The repository includes an offline ingestion pipeline that:

1. discovers candidate BVG ticket pages,
2. retrieves selected official pages,
3. extracts the main page content,
4. converts it to Markdown,
5. attaches provenance metadata, and
6. creates drafts requiring human review.

Automatically extracted pages are not inserted directly into the trusted
knowledge base. They are saved as Drafts. Reviewed documents are stored under `knowledge/domain/`
