# 0017: "All shelves" in the console chat

**Status:** accepted (2026-11-13)

## Context

The console chat searched one shelf, the one picked in the chat (remembered between visits). On 2026-11-12 a question about the customer FAQ was asked while the remembered shelf was `operations`, and the answer came from the wrong documents. The portal already searches several shelves at once (decision 0010).

## Decision

- The console shelf picker gets an **All shelves** option (shown when there is more than one shelf). It sends `all_shelves: true` to `POST /api/chat`, which searches every active shelf with the same `retrieve_many` as the portal.
- Unlike the portal, it includes shelves hidden from the portal: the console is the admin's view.
- The session is saved with no shelf (`collection_id` NULL). A console session without a shelf means "all shelves", so follow-ups keep searching all of them. Choosing one shelf again saves that shelf on the session. Every existing console session has a shelf, so no old session changes meaning.
- `all_shelves` wins over `collection_id` when both are sent.

## Consequences

- With all shelves searched, the 5 passages sent to the model are shared among them. A question about one shelf can lose a slot to similar text from another (in the 2026-11-12 portal answer, 3 of 5 sources came from `operations`). Picking one shelf is still the precise option.
- One vector query and one FTS query per shelf, and one embedding call per distinct embedding model.
