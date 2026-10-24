# Interface guidelines

## Review before action

The primary journey is a research queue followed by a briefing review. The review must show the company identity, editable Markdown, source references, relevant meeting context, and any incomplete research or unresolved facts.

Delivery and knowledge persistence are explicit actions. Present the exact briefing version, recipients, and action before authorization. Never preselect the sender as a recipient merely because their email triggered research. Editing content or recipients must clearly require renewed approval.

## Honest state

Distinguish queued/running work, an available draft, review required, an authorized action awaiting execution, a confirmed result, a failure, and an uncertain delivery outcome. Represent only states the backend can prove. A spinner ending does not prove delivery.

Show actionable failure information and preserve edits. An uncertain delivery requires reconciliation, so a generic retry button must not resend immediately. A partial report must expose missing evidence instead of looking complete.

## Evidence and reuse

Source references should open the supporting evidence and show retrieval time. Make approved knowledge distinguishable from a fresh unapproved draft. Let the owner correct ambiguous company associations and remove invalid knowledge without editing database identifiers.

## Consistent interaction

Use accessible semantic controls, keyboard navigation, visible focus, and textual state labels. Confirmations must be usable without relying on color. Loading, empty, permission-expired, validation-error, and provider-failure states belong to each feature's interaction contract.

Server state belongs to the API query layer; unsaved editor content remains local until saved. Background refresh must not overwrite an unsaved briefing edit. Shared components own repeated interaction patterns; feature modules own business-specific explanations.

Attachment-derived sources remain untrusted evidence in the briefing and cannot enter reusable knowledge without owner approval. PDF and Word exports represent the reviewed briefing version; exporting does not authorize delivery or knowledge persistence.
