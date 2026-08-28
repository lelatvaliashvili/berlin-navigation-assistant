# berlin-navigation-assistant


# Tools and Libraries

 - LangChain Infrastructure for its dedicated ChatOllama integration
 - LangChain's InMemoryVectorStore for cosine-similarity retrieval
 - Domain Specific Validators (Evidence sufficiency, Policy Grounding, Live Data, )
 - Guardrails AI for prompt-injection, jailbreak, PII and output validators

# Knowledge 

The repository includes an offline ingestion pipeline that:

1. discovers candidate BVG ticket pages,
2. retrieves selected official pages,
3. extracts the main page content,
4. converts it to Markdown,
5. attaches provenance metadata, and
6. creates drafts requiring human review.

Automatically extracted pages are not inserted directly into the trusted
knowledge base. Reviewed documents are stored under `knowledge/domain/`


# Walkthrough plan

1. Baseline system
knowledge → RAG retrieves evidence from documents.
journey → Transitous client works end-to-end to provide information.
departure → live data works end-to-end.
other (prompts including unrelated requests and information) → the assistant does not stay in scope

2. Evaluation dataset

run:  

python -m evaluation.run_conversation_scenarios
  --configuration baseline
for testing multi-turn conversations 


Cateogries in evaluation dataset include: 
KB-* - source-grounded cases
AMB-* - critical-context / ambiguity
INJ-* - adversarial injection
BCTRL-* - benign instruction controls
SCOPE-* - domain-boundary cases
LIVE-* - live-data cases

3. Baseline failures
4. Guardrail design
5. Guarded results
6. Metrics
7. Latency/cost trade-off
8. Remaining failures and Future Extensions


# Model Config

- Final assistant responses are limited to 256 generated tokens.
- Router responses are limited to 96 generated tokens.
- Ollama keeps the model loaded for 30 minutes to reduce repeated model-loading
  overhead during interactive use and evaluation.
- Only the latest six conversation messages are included in LLM context.
- The model context window is limited to 4096 tokens.
- RAG prompts are kept compact by removing unnecessary formatting and
  whitespace.

