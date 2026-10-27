# Candidate follow-up scenarios

This dataset extends [v3](../customer-examples-v3/README.md) without changing its historical run. It treats meeting-briefing relevance and the need for a reply as separate candidate judgments. It adds English and Vietnamese messages requesting our profile, proposing a discussion without a fixed agreement, and confirming a specific time.

The profile in `synthetic-our-capability-profile.txt` is a fictional fixture. When the other party requests our profile, the future draft should refer to our own selected profile. When the other party sends their profile, a reply should thank them and ask about a discussion, not attach their profile back. A meeting may only be scheduled when both parties have agreed to meet and the specific time, our own consent is verified independently of the sender's claim, and the applicable authorization workflow permits it.

The live interpretation run classifies follow-up intent. It does not draft or send email, access or attach files, verify consent, or create calendar events. The rubric's draft and scheduling guidance is a candidate expectation for a future workflow, not an evaluated or passed effect. No real company relationship, user, profile or appointment is represented.
