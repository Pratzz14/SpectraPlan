"""Append-only local enquiry history and chronological assessment events."""

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def now():
    return datetime.now(timezone.utc).isoformat()


def encode(value):
    return json.dumps(value, ensure_ascii=False)


def compose_description(description, answers):
    filled = [a for a in answers if a["answer"].strip()]
    if not filled:
        return description
    suffix = "\n\nCustomer clarifications:\n\n" + "\n\n".join(
        f"Context: {a['context']}\nQuestion: {a['question']}\nAnswer: {a['answer']}" for a in filled)
    # Accept older clients that already appended this exact clarification block.
    return description if description.endswith(suffix) else description + suffix


def question_id(run_id, question):
    from backend.knowledge_store import digest
    return digest({"run_id": run_id, "question": question["question"],
                   "context_ids": sorted(question["context_ids"])})[:24]


class HistoryConflict(ValueError):
    pass


class ExplainabilityStore:
    def __init__(self, path: Path):
        self.path = path
        self._initialized = False
        self._lock = threading.Lock()

    @contextmanager
    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys=ON")
            with self._lock:
                if not self._initialized:
                    connection.execute("PRAGMA journal_mode=WAL")
                    self._migrate(connection)
                    self._initialized = True
            with connection:
                yield connection
        finally:
            connection.close()

    def _migrate(self, connection):
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS enquiries (
                enquiry_id TEXT PRIMARY KEY, original_description TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS explainability_runs (
                run_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, description TEXT NOT NULL,
                clarification_answers TEXT NOT NULL, run_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS explainability_events (
                run_id TEXT NOT NULL REFERENCES explainability_runs(run_id) ON DELETE CASCADE,
                sequence INTEGER NOT NULL, stage TEXT NOT NULL, event_type TEXT NOT NULL,
                created_at TEXT NOT NULL, payload_json TEXT NOT NULL,
                PRIMARY KEY (run_id, sequence));
        """)
        existing = {row[1] for row in connection.execute("PRAGMA table_info(explainability_runs)")}
        for name, declaration in {"enquiry_id": "TEXT", "parent_run_id": "TEXT",
            "status": "TEXT NOT NULL DEFAULT 'complete'", "round_no": "INTEGER NOT NULL DEFAULT 1",
            "draft_description": "TEXT NOT NULL DEFAULT ''"}.items():
            if name not in existing:
                connection.execute(f"ALTER TABLE explainability_runs ADD COLUMN {name} {declaration}")
        # Old runs have no reliable parent link: preserve each as a standalone enquiry.
        connection.execute("""INSERT OR IGNORE INTO enquiries
            SELECT run_id, description, created_at, created_at FROM explainability_runs WHERE enquiry_id IS NULL""")
        connection.execute("""UPDATE explainability_runs SET enquiry_id=run_id, draft_description=description,
            status=COALESCE(json_extract(run_json, '$.run_status'), 'complete') WHERE enquiry_id IS NULL""")
        connection.execute("CREATE INDEX IF NOT EXISTS runs_by_enquiry ON explainability_runs(enquiry_id, round_no)")
        connection.commit()

    def begin(self, description, answers, *, enquiry_id=None, parent_run_id=None, run_id=None):
        run_id, timestamp = run_id or uuid4().hex, now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if enquiry_id:
                parent = connection.execute("SELECT * FROM explainability_runs WHERE run_id=? AND enquiry_id=?",
                                             (parent_run_id, enquiry_id)).fetchone()
                if parent is None:
                    raise HistoryConflict("Select a saved parent run from this enquiry.")
                if parent["status"] == "running":
                    raise HistoryConflict("The selected parent analysis is still running.")
            else:
                if parent_run_id:
                    raise HistoryConflict("A parent run requires an enquiry ID.")
                enquiry_id = uuid4().hex
                connection.execute("INSERT INTO enquiries VALUES (?, ?, ?, ?)",
                                   (enquiry_id, description, timestamp, timestamp))
            for answer in answers:
                origin = answer.get("origin_run_id")
                qid = answer.get("question_id")
                if not origin and not qid:
                    continue  # Legacy clients: retain the supplied wording as unlinked answers.
                row = connection.execute("SELECT run_json FROM explainability_runs WHERE run_id=? AND enquiry_id=?",
                                         (origin, enquiry_id)).fetchone()
                source_run = json.loads(row[0]) if row else {}
                questions = (source_run.get("assessment") or {}).get("clarification_questions", [])
                question = next((q for q in questions if question_id(origin, q) == qid and q["question"] == answer["question"]), None)
                if question is None:
                    raise HistoryConflict("Clarification answer does not match a question in this enquiry.")
                contexts = (source_run.get("facts") or {}).get("contexts", [])
                labels = []
                for cid in question["context_ids"]:
                    context = next((c for c in contexts if c["context_id"] == cid), None)
                    label = context["label"] if context else cid
                    duplicates = [c for c in contexts if c["label"] == label]
                    if len(duplicates) > 1:
                        ordinal = duplicates.index(context)
                        position = ["first", "second", "third", "fourth"][ordinal] if ordinal < 4 else "additional"
                        label += f" ({position} stream)"
                    labels.append(label)
                answer["context"] = " · ".join(labels) if labels else "Shared / all contexts"
            round_no = connection.execute("SELECT COALESCE(MAX(round_no),0)+1 FROM explainability_runs WHERE enquiry_id=?",
                                          (enquiry_id,)).fetchone()[0]
            effective = compose_description(description, answers)
            connection.execute("""INSERT INTO explainability_runs
                (run_id,created_at,description,clarification_answers,run_json,enquiry_id,parent_run_id,status,round_no,draft_description)
                VALUES (?,?,?,?,?,?,?,'running',?,?)""",
                (run_id,timestamp,effective,encode(answers),'{}',enquiry_id,parent_run_id,round_no,description))
            connection.execute("UPDATE enquiries SET updated_at=? WHERE enquiry_id=?", (timestamp,enquiry_id))
        self.append(run_id, {"stage":"input","event_type":"run_started", "payload":{
            "description":description,"effective_description":effective,"clarification_answers":answers}})
        return {"run_id":run_id,"enquiry_id":enquiry_id,"parent_run_id":parent_run_id,"round_no":round_no,
                "effective_description":effective}

    def append(self, run_id, event):
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            sequence = connection.execute("SELECT COALESCE(MAX(sequence),-1)+1 FROM explainability_events WHERE run_id=?",
                                          (run_id,)).fetchone()[0]
            connection.execute("INSERT INTO explainability_events VALUES (?,?,?,?,?,?)", (
                run_id,sequence,event.get("stage") or "unknown",event["event_type"],
                event.get("created_at") or now(),encode(event.get("payload",{}))))

    def finish(self, run_id, run):
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            updated = connection.execute("UPDATE explainability_runs SET run_json=?,status=? WHERE run_id=? AND status='running'",
                                         (encode(run),run.get("run_status", "complete"),run_id))
            if updated.rowcount != 1:
                raise HistoryConflict("A finished analysis cannot be replaced. Create a new round.")
            connection.execute("UPDATE enquiries SET updated_at=? WHERE enquiry_id=(SELECT enquiry_id FROM explainability_runs WHERE run_id=?)",
                               (now(),run_id))
            sequence = connection.execute("SELECT COALESCE(MAX(sequence),-1)+1 FROM explainability_events WHERE run_id=?",(run_id,)).fetchone()[0]
            connection.execute("INSERT INTO explainability_events VALUES (?,?,?,?,?,?)",(run_id,sequence,"result","run_finished",now(),
                encode({"status":run.get("run_status", "complete"),"errors":run.get("errors",[])})))

    def interrupt(self, run_id, reason="Analysis interrupted before completion"):
        with self._connect() as connection:
            connection.execute("UPDATE explainability_runs SET status='interrupted' WHERE run_id=? AND status='running'", (run_id,))
        self.append(run_id,{"stage":"result","event_type":"run_interrupted","payload":{"message":reason}})

    def recover_interrupted(self):
        with self._connect() as connection:
            ids = [row[0] for row in connection.execute("SELECT run_id FROM explainability_runs WHERE status='running'")]
        for run_id in ids:
            self.interrupt(run_id,"Application restarted before this analysis completed")

    def save(self, run_id, description, clarification_answers, run, events):
        """Compatibility import for existing diagnostics. Never replaces a saved run."""
        self.begin(description,clarification_answers,run_id=run_id)
        for event in events:
            self.append(run_id,event)
        self.finish(run_id,run)

    def read(self, run_id):
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM explainability_runs WHERE run_id=?",(run_id,)).fetchone()
            if row is None:
                return None
            events = connection.execute("SELECT * FROM explainability_events WHERE run_id=? ORDER BY sequence",(run_id,)).fetchall()
        result = dict(row)
        result["run"] = json.loads(result.pop("run_json")) or None
        result["clarification_answers"] = json.loads(result["clarification_answers"])
        result["events"] = [{"sequence":e["sequence"],"stage":e["stage"],"event_type":e["event_type"],
            "created_at":e["created_at"],"payload":json.loads(e["payload_json"])} for e in events]
        if result["run"] and result["run"].get("assessment"):
            result["questions"] = [{**q,"question_id":question_id(run_id,q),"origin_run_id":run_id}
                                   for q in result["run"]["assessment"]["clarification_questions"]]
        else:
            result["questions"] = []
        return result

    def list_enquiries(self, limit=50, offset=0):
        with self._connect() as connection:
            return [dict(row) for row in connection.execute("""SELECT e.*, COUNT(r.run_id) AS rounds,
                (SELECT run_id FROM explainability_runs WHERE enquiry_id=e.enquiry_id ORDER BY round_no DESC LIMIT 1) AS latest_run_id
                FROM enquiries e JOIN explainability_runs r USING(enquiry_id) GROUP BY e.enquiry_id
                ORDER BY e.updated_at DESC, e.enquiry_id LIMIT ? OFFSET ?""",(limit,offset))]

    def enquiry(self, enquiry_id):
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM enquiries WHERE enquiry_id=?",(enquiry_id,)).fetchone()
            if row is None:
                return None
            runs = [dict(r) for r in connection.execute("""SELECT run_id,created_at,status,round_no,parent_run_id
                FROM explainability_runs WHERE enquiry_id=? ORDER BY round_no""",(enquiry_id,))]
        return {**dict(row),"runs":runs}
