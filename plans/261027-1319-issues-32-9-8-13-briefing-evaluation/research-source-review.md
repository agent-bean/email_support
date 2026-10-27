# Customer research source review

This is a candidate, manual triage of the 2026-10-27 read-only run, not a reviewed company briefing or a factual baseline. The search log contains the 18 queries and returned sources; the refetch log records every attempted URL and its result. Both logs are private under `apps/backend/evals/results/`, named `customer-research-live-20261027T101432Z.jsonl` and `customer-refetch-live-20261027T101541Z.jsonl`. No factual claim has been approved from these results.

| Company | Overview | Products/services | News |
| --- | --- | --- | --- |
| FPT Software | LeadIQ page fetched; third-party company match requires verification. | LinkedIn page fetched but begins with a consent notice; inspect the actual extract before treating it as evidence. | Official newsroom listing fetched; select a dated individual article before using it. |
| Vinamilk | No candidate source fetched. | Official annual-report page fetched; it covers 2023, so it is not evidence of current offerings without corroboration. | Company press release fetched; publication date and current relevance require checking. |
| Samsung Vietnam | LinkedIn page fetched but begins with a consent notice; content sufficiency is unverified. | Third-party directory page for Samsung Electronics Vietnam Thai Nguyen fetched; confirm it is the requested entity and supports the specific claim. | Third-party article fetched; verify date, identity and relevance before use. |
| Shopee Vietnam | No candidate source fetched. | No candidate source fetched. | Parent-company news page fetched; verify the article concerns the Vietnam operation and the claim. |
| Viettel Solutions | Employee-directory page fetched; distinguish the named business from the wider group and verify content. | No candidate source fetched. | Third-party article about Viettel Group fetched; group coverage is not automatically evidence about Viettel Solutions. |
| Bosch Global Software Technologies Vietnam | No candidate source fetched. | No candidate source fetched. | Company overview page fetched; it is not demonstrably a recent news article. |

All 54 search-source records have unknown `published_at` in this run. A fetch success only means that bounded text was returned; consent pages, corporate directory pages, parent-company material and old reports must not automatically pass source relevance, freshness or factual support. For each eventual briefing claim, a reviewer must identify an appropriate source passage, verify the correct entity and publication date, and decide whether the passage supports the claim. There are no generated briefing claims in this run to assess.
