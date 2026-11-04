"""Postgres persistence using the existing, tested history business rules."""
from contextlib import contextmanager
import json
import re
from backend.services.history.explainability import ExplainabilityStore


class Row(dict):
    def __getitem__(self, key):
        return list(self.values())[key] if isinstance(key, int) else super().__getitem__(key)


class Cursor:
    def __init__(self, cursor):
        self.cursor, self.rowcount = cursor, cursor.rowcount

    def _row(self, values):
        if values is None:
            return None
        result = Row(zip((c.name for c in self.cursor.description), values))
        for key in ("run_json", "clarification_answers", "payload_json"):
            if key in result:
                result[key] = json.dumps(result[key], ensure_ascii=False)
        return result

    def fetchone(self):
        return self._row(self.cursor.fetchone())

    def fetchall(self):
        return [self._row(r) for r in self.cursor.fetchall()]

    def __iter__(self):
        return iter(self.fetchall())


class HistoryConnection:
    """Translate only the small SQLite SQL dialect used by ExplainabilityStore."""
    def __init__(self, connection):
        self.connection = connection

    def execute(self, query, parameters=()):
        if query == "BEGIN IMMEDIATE":
            return None  # Database.connection already wraps a transaction.
        if "SELECT COALESCE(MAX(sequence)" in query:
            self.connection.execute("SELECT run_id FROM spectraplan.explainability_runs WHERE run_id=%s FOR UPDATE", parameters)
        if "SELECT COALESCE(MAX(round_no)" in query:
            self.connection.execute("SELECT enquiry_id FROM spectraplan.enquiries WHERE enquiry_id=%s FOR UPDATE", parameters)
        # Preserve literal substring semantics; %, _ and backslash are never wildcards.
        query = query.replace("instr(lower(COALESCE(e.customer_email, '')), lower(?))",
                              "strpos(lower(COALESCE(e.customer_email, '')), lower(?))")
        for table in ("explainability_runs", "explainability_events", "enquiries"):
            query = re.sub(r"(?<![\w.])" + table + r"\b", "spectraplan." + table, query)
        query = query.replace("?", "%s")
        # Additional lease column must not change the public history response.
        cursor = Cursor(self.connection.execute(query, parameters))
        return cursor


class PostgresHistory(ExplainabilityStore):
    def __init__(self, database):
        self.database = database

    @contextmanager
    def _connect(self):
        with self.database.connection() as connection:
            yield HistoryConnection(connection)

    def begin(self, *args, **kwargs):
        result = super().begin(*args, **kwargs)
        self.heartbeat(result["run_id"])
        return result

    def heartbeat(self, run_id):
        with self.database.connection() as c:
            c.execute("UPDATE spectraplan.explainability_runs SET lease_until=now()+interval '10 minutes' "
                      "WHERE run_id=%s AND status='running'", (run_id,))

    def append(self,run_id,event):
        super().append(run_id,event)
        self.heartbeat(run_id)

    def recover_interrupted(self):
        # Lock expired runs before changing them. Never interrupt another live API instance.
        with self.database.connection() as c:
            rows = c.execute("UPDATE spectraplan.explainability_runs SET status='interrupted' "
                "WHERE status='running' AND lease_until < now() RETURNING run_id").fetchall()
            for (run_id,) in rows:
                sequence = c.execute("SELECT COALESCE(MAX(sequence),-1)+1 FROM spectraplan.explainability_events WHERE run_id=%s", (run_id,)).fetchone()[0]
                c.execute("INSERT INTO spectraplan.explainability_events VALUES (%s,%s,'result','run_interrupted',%s,%s)",
                    (run_id, sequence, __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),
                     '{"message":"Assessment heartbeat expired"}'))

    def read(self, run_id):
        result = super().read(run_id)
        if result:
            result.pop("lease_until", None)
        return result
