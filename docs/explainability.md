# Enquiry history and explainability

Each accepted `POST /api/assess` creates a durable analysis round before model
processing starts. SQLite storage uses `EXPLAINABILITY_DB_PATH` (default
`outputs/assessment/explainability.sqlite`). Histories are local and remain until
explicitly removed. They contain enquiry and source content and should be kept
with the same care as the original enquiries; credentials and authorization
headers are excluded. Automated traces establish what happened, not scientific
correctness or human approval.

## Continuing an enquiry

Send `description` as the current enquiry text, with `clarification_answers` kept
separate. Each answer contains `question`, `context`, `answer`, and, for linked
questions, `question_id` and `origin_run_id`. The response metadata returns
`enquiry_id`, `run_id`, `parent_run_id`, `round_no` and `question_ids` in the same
order as the assessment questions. Submit `enquiry_id` and `parent_run_id` to add
a round. Linked answers must match an issued question in that enquiry; the server
uses its saved context, then assembles the effective model input. Plain
`description` requests and older unlinked answers remain supported.

The saved original enquiry, each submitted revision, effective input, answers,
issued questions and final result are retained. Existing databases migrate each
legacy run into a separate enquiry without inventing parent links or timestamps.

## Reading history

- `GET /api/enquiries?limit=50&offset=0` lists saved enquiries, newest first.
- `GET /api/enquiries/{enquiry_id}` lists the immutable analysis rounds.
- `GET /api/assess/{run_id}/explainability` returns the round, raw stored result,
  questions with stable identifiers, and chronological events. An unfinished run
  has `run: null`; its recorded events remain available.

The top navigation has a separate **History** page for saved enquiries, round
selection, explainability and trace export. It does not replace the current
chemist enquiry when inspecting a previous run. **Continue in Assessment**
reopens a selected run for further clarification. **New enquiry** starts a clean
assessment without deleting saved history. The Assessment page contains the
chemist enquiry, clarification questions and scientific results.

## Recorded events

Events are appended when they occur, including model requests, raw responses
before validation, failures, validation feedback, repairs, fallback identities,
validated stages and final outcomes. Requests include their schemas and prompts;
responses include usage, timing and returned model identity. Source-search events
record the exact BM25 tokens, synonym expansion, embedding input/model, pinned
corpus version, candidate filenames, branch rankings and scores, admission reasons,
selected evidence and content passed to synthesis. Synthetic availability probes
are identified separately in provider-attempt metadata.

If processing is cancelled, partial events remain. On startup, the local
single-process application marks leftover running rounds interrupted. Tests use
automatically isolated temporary databases. A storage failure is explicit; the
application does not start provider work when it cannot create a durable run.
