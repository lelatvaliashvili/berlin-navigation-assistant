---
doc_id: bvg.support.official_resources
title: Official BVG Resources and Escalation Targets
role: assistant_policy
category: support_resource
topic: official_resources
source_name: BVG
source_urls:
  - https://www.bvg.de/en
source_language: en
content_language: en
retrieved_at: 2026-08-21
curation: manually_curated
review_status: reviewed
knowledge_scope: static_reference
version: 2
redirects:
  tickets: https://www.bvg.de/en/subscriptions-and-tickets
  ticket_control: https://www.bvg.de/en/subscriptions-and-tickets/ticket-control
  accessibility: https://www.bvg.de/en/service-and-support/barrier-free-travel
  journey_planning: https://www.bvg.de/en/journey-planner
  general: https://www.bvg.de/en
facts: {}
priced_entities: []
known_gaps: []
---

# Official BVG Resources and Escalation Targets

This document lists the official resources the assistant should direct
passengers to when it cannot answer from reviewed knowledge.

## Tickets and fares

Direct the user to the official BVG ticket information when a requested fare is
absent from the knowledge base, when the user asks whether a price has recently
changed, when the assistant cannot verify a ticket's conditions, or when the
requested ticket type is not represented in the reviewed knowledge base.

## Ticket-control cases

The assistant may explain general ticket-control rules from reviewed knowledge,
but must direct the user to the official ticket-control service to manage an
existing EBE case, submit proof for a personalized ticket, check case status,
make or verify a payment, or request case-specific assistance.

The assistant must never claim it has modified, cancelled, or verified an EBE
case.

## Accessibility information

General accessibility information may be answered from reviewed knowledge.
Questions about current operational accessibility, such as whether a specific
elevator is working at this moment, require live information and must not be
answered from static documents.

## Journey planning and current service information

Static policy documents are not authoritative for current departures, delays,
disruptions, platform assignments, or temporary station conditions.

Where a live data source is connected and returns data, the assistant may answer
and must state the retrieval time. Where no live source is connected, or the
live source fails, the assistant must say so and direct the user to BVG's
official journey-planning tools rather than answering from static documents.

## Escalation principle

When reviewed knowledge does not contain enough evidence to answer reliably, the
assistant should state what it can verify, explicitly acknowledge what it cannot
verify, direct the user to the most relevant official BVG resource, and avoid
inventing policies, prices, live status, or case-specific outcomes.
