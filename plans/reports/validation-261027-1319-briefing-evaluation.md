# Joint plan validation record

Date: 2026-10-27, Asia/Bangkok. Flags: `--tdd --hard --yagni`. Current scope: #32, #9, #8, #13. This records planning decisions, not application verification or owner acceptance of an implementation.

## Owner decisions

The owner approved one plan with separate sequential PRs for #32, #9 and #13, then explicitly added the complete #8 scope: “Khoan đã, thế thì làm luôn cái 8 cùng lúc đi”. The current sequence is therefore #32, #9, #8, #13. Preserve all four Issues' acceptance criteria. Native dependencies can be satisfied without edits.

The owner clarified that evaluation is a development/pre-release activity. Live evaluation means an explicitly invoked development run against real providers, not a recurring production monitor. Offline regression remains separate.

### Earlier staging decision, superseded

Question: “GitHub hiện đặt #8 (phân tích email và nhận diện công ty) làm dependency chặn #13, nhưng nội dung #13 cho phép chạy từ input đã chuẩn hoá. Với kế hoạch ba issue đã chốt, bạn muốn xử lý thế nào?”

Options:
1. Dùng input chuẩn hoá có công ty được chọn rõ; lập đề xuất chỉnh dependency để #13 không chờ #8 (khuyến nghị).
2. Giữ dependency; lập kế hoạch cả ba nhưng chỉ thực hiện #13 sau khi #8 hoàn tất.

Owner asked: “Option 1 thì rủi ro là gì”. The explanation covered clean-input evidence limits, possible contract drift on subsequent #8 integration, unresolved identity stopping research, and #8 remaining required for release.

Follow-up question: “Với các giới hạn trên, bạn chọn hướng nào cho kế hoạch? #8 vẫn giữ nguyên phạm vi và yêu cầu tích hợp khi hoàn thiện release.”

Options:
1. Option 1: làm #13 từ input chuẩn hoá; ghi rõ giới hạn eval và đề xuất chỉnh dependency (khuyến nghị).
2. Giữ dependency #8; kế hoạch #13 phải chờ #8 hoàn tất.

Owner selected Option 1, then superseded the staging choice by including #8 itself. Do not carry the proposed dependency bypass or #8 exclusion into the current plan.

## Scope challenge

The owner settled scope before planning. Reuse that decision; do not ask the expansion/hold/reduction fork again. Apply `--yagni` to eliminate unrequested platforms, UI, synchronization, scheduler, graph/vector projection, delivery and production infrastructure. Four phases are justified by four separate Issue/PR acceptance boundaries; TDD verification belongs inside every phase.

## Research and source verification

Read the actual Issue criteria and native dependencies with `gh`, repository documentation, manifests, persistence code, migration/backup harness, and current skill/CLI help. Two research agents consulted primary provider and LangGraph sources. See [source map](scout-261027-1319-briefing-evaluation.md), [provider research](researcher-261027-1319-provider-tools.md), and [workflow/identity research](researcher-261027-1322-workflow-evaluation.md).

Research preceded drafting and review; document verification is recorded below. No tests, package installation, source-code changes, live-provider calls, database mutation or GitHub update has been performed.

## Red-team review

Completed three independent reviews: security, assumptions/scope and failure modes. Forty overlapping claim samples checked (12+12+16); this is not 40 unique claims. Three deduplicated findings: outbound private-data boundary, revoked-knowledge recovery, and special-use fixture validator incompatibility. One citation correction accompanies the third. See [full adjudication and source evidence](red-team-261027-1319-briefing-evaluation.md).

The owner was asked whether to apply all three proposed changes and the citation correction, review individually, or retain the draft. Answer: “Áp dụng tất cả (khuyến nghị)”. Applied to all affected plan phases and acceptance/risk/test instructions with red-team update markers. This authorizes plan corrections only; owner plan acceptance and implementation remain separate.

## Final validation and handoff

`ak plan validate plans/261027-1319-issues-32-9-8-13-briefing-evaluation --json` passed. Static local-link inspection found zero broken links across five plan files. Final folder indexed and selected with `ak plan update`/`ak plan use`; all implementation checkboxes stay unchecked. No live task-management surface is available, so the plan checkboxes/dependencies remain the durable task view. No session-owned background process was started or needs stopping.

### Whole-Plan Consistency Sweep

Completed after the owner-approved fixes: re-read `plan.md` and all four phase files, reconciled each decision delta across requirements, steps, test matrices, acceptance and risk notes, and checked canonical authority/recovery/pause paths. Unresolved contradictions: 0. Superseded scope language remains only as explicitly superseded history. No obsolete fixture-domain or source-citation instruction remains in phase files.

Actual checks: repeated `ak plan validate ... --json` passed; static checks found five plan files, four phase files, valid local links/frontmatter, no superseded instruction matches and no completed implementation checkboxes. The index is 68 lines. Phase dependencies are ordered without cycles, and sequential shared-file ownership is retained. Plan tasks remain in durable unchecked acceptance lists because no runtime task surface is available. No app test, provider or database command was run for these documentation edits.

Plan is ready for explicit owner approval. After approval, execution handoff is `/ak:cook plans/261027-1319-issues-32-9-8-13-briefing-evaluation/plan.md --yagni`. No automatic execution flag is authorized. No implementation, merge, Issue closure or release authorization is inferred from this planning record.
