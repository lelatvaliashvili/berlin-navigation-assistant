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
3. Baseline failures
4. Guardrail design
5. Guarded results
6. Metrics
7. Latency/cost trade-off
8. Remaining failures and Future Extensions