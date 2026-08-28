# baseline, knoweledge base curation 

The baseline therefore provides the capabilities required for a useful Berlin
mobility assistant, while avoiding guardrail-specific enforcement. It supports:

- BVG ticket and policy questions through retrieval-augmented generation (RAG)
- live journey planning and departure information through Transitous
- conversational follow-up handling
- intent routing between knowledge, journey, departure, and unsupported requests


# small curated dataset of test cases, with the aim to identify weak points and potential failures.

## Knowledge Base Curation

The RAG knowledge base is intentionally small and domain-specific. It is derived
from official BVG sources covering areas such as tickets, fare zones, passenger
rules, accessibility, and transport policies.

A lightweight offline ingestion pipeline is used to discover BVG pages, retrieve
their contents, convert relevant page content to Markdown, and attach provenance
metadata. Automatically extracted pages are treated as curation drafts rather
than being inserted directly into the trusted knowledge base.

Only reviewed documents are used by the runtime retrieval system.

This approach was chosen instead of using a large general-purpose corpus because
the application operates in a narrow domain where source authority and factual
traceability

