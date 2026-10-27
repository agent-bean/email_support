# Issue 5/6 plan validation

Plan: [Owner access and Google connection](../261026-1714-issue-5-6-owner-google-access/plan.md). Date: 2026-10-26, Asia/Bangkok. Flags: `--hard --tdd --yagni`. This record validates planning accuracy; it does not establish implemented behavior, runtime acceptance or permission to merge/deploy.

## Reused accepted brainstorm contract

- Outcome: owner-only Google OIDC and application sessions (#5), followed by separate Gmail/Calendar connection lifecycle (#6).
- Constraints: one owner, same Google identity for login and connection, read-only shared/secondary Calendar access, server-side credentials, existing FastAPI/React/PostgreSQL and generated contracts.
- Non-goals: multiuser/accounts, Redis, sync/jobs, real sending, production deployment or publishing the plan to GitHub.
- Acceptance: original Issue #5/#6 criteria, browser/session/protocol failure tests, encrypted tokens, refresh/disconnect concurrency, actionable UI and real Google read/revoke smoke for #6.
- Trade-off: keep Issue #5 independently reviewable before #6; combining code would enlarge the authentication review surface. The assumption is a stable session/owner contract from #5; if #6 cannot bind its callback safely, adjust the boundary before proceeding. No better alternative to the requested separate login/consent responsibilities was found in current source/Issue evidence.
- Scope challenge: reuse the completed brainstorm; cut unrequested infrastructure/frameworks while retaining all original acceptance criteria. More than eight files is justified by typed HTTP, protocol/service/storage boundaries, additive migrations, UI and tests; no generic class hierarchy is required.

## Validation session 1

### Decisions from the owner

The owner confirmed in the preceding brainstorm:

1. Question: “Tài khoản Gmail/Calendar có phải chính tài khoản Google dùng đăng nhập app không?” Options: “Cùng tài khoản (đề xuất cho phạm vi nhỏ nhất)” | “Cho phép một tài khoản Google khác do owner kết nối”. Answer: “Cùng tài khoản (đề xuất cho phạm vi nhỏ nhất)”. Impact: compare verified consent `sub` to both the live owner session and configured owner.
2. Question: “Calendar cần đọc những lịch nào trong phạm vi hiện tại?” Options: “Chỉ lịch chính của tài khoản (đề xuất)” | “Cả lịch được chia sẻ hoặc lịch phụ”. Answer: “Cả lịch được chia sẻ hoặc lịch phụ”. Impact: require Calendar events/read-only calendar-list scopes; do not restrict to owned/primary calendars.

### Session lifetime question

- Full question: “Plan đề xuất phiên đăng nhập hết hạn sau 12 giờ, không tự kéo dài khi sử dụng; sau đó owner đăng nhập lại. Bạn muốn thời hạn nào?”
- Options: “12 giờ (đề xuất)” | “24 giờ” | “7 ngày”.
- Answer, verbatim: “accessToken, refreshToken mà nhỉ?\nOption 1”.
- Confirmed decision: 12-hour absolute application-session lifetime, without sliding renewal.
- Clarification given: Google access/refresh tokens belong to the provider connection (#6); the opaque browser session belongs to app login (#5). Expiring/logout of app session does not itself disconnect Google.
- Impact: phase 1 session/cookie expiry, phase 2 expiry UI/tests and phase 3 independent credential lifecycle.

## Research adjudication

Research is evidence rather than automatic design authority. Corrected the connection report's original Gmail classification: `gmail.readonly` is restricted; `gmail.send` is sensitive. Corrected its original memory-only access-token recommendation to an encrypted credential bundle, because process-local tokens cannot support coherent cross-process refresh reuse. Final phase design chooses the smallest authenticated encryption API and supersedes broader research suggestions for optional idle timers, session peppers and incremental feature-consent UI.

## Red-team adjudication

Independent [security](review-security-261026-1714-owner-google-access.md), [assumption/scope](review-assumptions-261026-1714-owner-google-access.md) and [failure](review-failures-261026-1714-owner-google-access.md) reviews are complete. Eight submitted findings reduce to five after merging the repeated revoke and runtime findings. Controller assessment: 1 High, 4 Medium; all five were proposed and subsequently approved in validation session 2, with no change to accepted account/calendar/session choices.

| Finding | Severity | Approved disposition | Affected phase |
| --- | --- | --- | --- |
| Delayed revoke can invalidate a newer grant | High | Accepted and applied | 3 |
| Preflight cannot guarantee a send-time cutoff | Medium | Accepted; admission semantics approved | 3 and index |
| Ordinary access-token expiry can masquerade as revoke success | Medium | Accepted and applied | 3 |
| Duplicate restore-on-every-migrate workflow; missing explicit empty/no-op branch | Medium | Accepted and applied under `--yagni` | 2 and 3 |
| Live-session guard needs explicit locking against logout | Medium | Accepted and applied as execution-detail clarification | 1 and 3 |

### Approved deltas applied to the phase files

1. **Serialize revocation and reconnect.** Add a durable revoke-operation marker on the connection row in the same commit as block/purge. Refuse consent start/promotion while revocation is in progress. A deadline/crash changes it to unresolved/unknown rather than automatically unlocking. Require explicit operator recovery and confirmation of Google grant cleanup before clearing an unknown state; do not resume old revoke dispatch after a newer consent. Add coordinated delayed-revoke/reconnect and crash tests. Keep this on the existing connection row; no worker/job infrastructure.
2. **Define provider-work admission.** A successful short transaction authorizing a bounded operation is its admission point. Disconnect blocks every admission after its committed block. An operation admitted earlier counts as in flight even if network dispatch has not yet happened; cancel where possible and discard stale results. Do not promise an absolute HTTP-send cutoff without cross-process network serialization. Add a deterministic pause between admission and HTTP, and document that admitted work can finish externally while its local result is discarded. The owner approved this replacement of the stronger draft wording.
3. **Prove revocation independently of expiry.** Before disconnect, require the tested access token to remain valid beyond the 10-second disconnect deadline plus the entire 120-second observation window plus at least 30 seconds of clock margin (strictly more than 160 seconds); refresh first when necessary. Record a successful read immediately before disconnect. Credential rejection after natural expiry, or a transient provider error, is not revocation proof and leaves verification pending. Test this false-positive path with a controlled clock/provider double.
4. **Simplify the local runtime route.** Keep the separate persistent auth DB, private configuration, deterministic ports, ownership guards and migration-before-API ordering. Back up and validate an archive before every actual schema mutation, including the empty initial database. Skip mutation/backup when already at head. For an empty DB, validate the dump/base state without requiring an Alembic row or representative data; do not misclassify a failed revision query as an empty database. Remove mandatory temporary restore/revision/row rehearsal from each normal `up`/migration. Reuse the existing real-DB restore suite and add a real disposable-runtime exercise of the new route for initial install, no-op, upgrade and backup failure. Preserve backups and fail closed on errors; never point the test harness at runtime data.
5. **Make the session guard atomic against logout.** Final consent promotion locks and validates the referenced session row in the same short transaction as the generation-conditional connection write; logout deletion conflicts with that lock. Use one lock order (session, then connection), no provider HTTP while locks/transactions are held, and a PostgreSQL barrier test at the final-write boundary. The draft already requires a live-session-guarded write, so this is downgraded from the reviewer's High to Medium specificity rather than treated as a proven implemented vulnerability.

The mandatory backup rule is retained for every schema/data mutation; the approved cut removes repeated recovery rehearsal while preserving backup and real database verification. No accepted product feature is cut.

## Validation session 2

- Full question: “Bạn muốn xử lý 5 chỉnh sửa trong báo cáo validation thế nào? Đề xuất áp dụng cả 5, gồm: chặn reconnect khi revoke còn chạy/unknown; Disconnect chặn công việc được nhận mới (việc đã nhận có thể đang chạy, kết quả cũ bị bỏ); smoke chỉ tính revoke khi token chưa đến hạn; bỏ restore lặp mỗi migration nhưng giữ backup; khóa session để callback không ghi sau logout.”
- Options: “Áp dụng cả 5 (đề xuất)” | “Cho tôi xem xét từng điểm” | “Giữ nguyên plan hiện tại”.
- Answer, verbatim: “Áp dụng cả 5 (đề xuất)”.
- Applied: phase 1 specifies session-lock/logout serialization; phase 2 removes repeated restore rehearsal and defines initial/head/upgrade/failure branches with real route coverage; phase 3 specifies durable revoke gating, operation admission, session/connection lock ordering and smoke lifetime requirements. Index acceptance matches the approved semantics.
- Added protocol execution detail from the owner-access research: concrete Authlib primitives without `request.session`, explicit issuer/audience options, missing-token rejection and bounded JWKS behavior.

## Verification results

AgentKit structural validation passed after the approved corrections. Parsing found 3 sequential phases, 48 unchecked implementation tasks and 0 completed tasks. All 37 local Markdown links/anchors/line bounds across the index, phase files and validation record passed; the index remains 59 lines, with no scaffold placeholders. AgentKit reindex recognized the existing plan without duplication; worktree pin and phase checkboxes retain execution state. No applicable live task-management surface was available. All implementation tasks remain unchecked. No application tests, provider smoke, database mutation or production operation was run in this planning session.

### Whole-plan consistency sweep

All four plan files were read; the changed contracts and test matrices were checked after correction. Same owner, shared/secondary calendars, 12-hour app session separate from Google credentials, independent #5 delivery boundary, credential-free health/default smoke and no real sending are preserved. All five owner-approved deltas are propagated into contracts, execution steps and test scenarios. Operational OAuth setup and live acceptance remain pending prerequisites for execution, not unresolved product decisions.
