# Reflection

## What worked well

The layered design worked well in practice. Deterministic checks handle
missing journey information and obvious evidence problems, while model-based
checks handle semantic risks such as prompt injection, scope, and unsupported
claims. A guarded response can ask a focused question or preserve supported
information instead of defaulting to a refusal.

Curating the knowledge base was also an important part of the work. I wanted
answers to come from the reviewed documents in the custom knowledge directory,
not only from the model's general memory. Using reviewed BVG material with
provenance gives the model a constrained evidence base and makes answers easier
to inspect.

## Chellenges

The interesting challenge was defining evaluation criteria in a setting where
“correct” can have different forms in a conversational answer. Exact phrase
checks are deterministic and reproducible, but they can reject a good
paraphrase or mark a helpful answer as a failure because it uses different
wording.

For this benchmark, semantic judging was a clearer measure of answer quality
because of overly restrictive deterministic success criteria in responses.

For example, a safe answer may refuse a claimed authority, ask for missing journey details, or qualify an
unsupported fare without using one prescribed phrase. The semantic judge can
recognize those outcomes. I therefore keep semantic and
deterministic results separate and manually inspect disagreements.

Another difficulty was separating a safer system outcome from correct
guardrail attribution. In some cases one guard prevented a failure associated
with another guard. This was still useful defense in depth, but it would be
misleading to claim that the named guardrail caused the improvement. Recording
the observed trigger made that distinction visible.

Live journey requests created a related evaluation challenge. Transitous data
depends on an external service and current time, while the safety question is
whether origin, destination, and station fields were resolved before the tool
was called. Treating that precondition as a separate check made the result more
meaningful, but also exposed routing and place-resolution edge cases.

## Current limitations and next steps

The benchmark and knowledge base are intentionally small, so the results show
behavior on the tested scenarios rather than general safety guarantees. The
guarded path also performs additional model calls, which can make the
interaction feel slower. I would investigate parallelizing independent checks,
using smaller models for low-risk classification, and selectively applying
expensive checks while validating every change against an unseen holdout set.

For a more robust production pipeline, I would add independently authored
paraphrase and red-team holdouts, repeated runs with confidence intervals, and
human review for high-impact or ambiguous cases. I would also add telemetry for
latency, cost, guardrail triggers, and false positives. The knowledge sources
would need versioning, freshness monitoring, and a review workflow to prevent
stale policy information from entering the trusted corpus.

Authentication, rate limiting, PII handling, retries, circuit breakers, and
model/prompt version pinning would further reduce operational and security
risks.

Overall, the main lesson from the challenge is that guardrails are not a
single filter around an LLM. They are a measured, evolving part of the
application, the knowledge pipeline, and the user experience.
