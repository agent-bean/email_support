# Candidate follow-up boundaries

This dataset extends [v6](../customer-examples-v6/README.md); earlier datasets and inputs remain unchanged. All expectations are candidates pending owner review, not approved golden labels. Shopee's OCR inquiry calls for a reply, but has no meeting or briefing context, so its candidate meeting-briefing relevance is uncertain. This change reflects the supplied email, not the outcome of a model run.

Three synthetic bilingual pairs distinguish a possible future revisit (uncertain follow-up), an explicit service question (reply), and a receipt explicitly requiring no reply (none). None establishes a meeting. These are controls for interpretation, not evidence of real relationships.

The fictional `synthetic-our-capability-profile.txt` and v5's profile and scheduling guidance remain applicable. Interpretation classifies intent only: it does not draft or send email, access attachments, verify consent, or create calendar events. Those future workflow effects are not evaluated.

FPT asks to learn about AI solutions but does not request a meeting, discussion, or briefing. Its candidate meeting-briefing relevance is therefore uncertain and its candidate follow-up is reply, consistently with the stated policy and independent of model output.
