"""Bounded Postgres connections with sanitized failures and verified TLS."""
from contextlib import contextmanager
from pathlib import Path
import threading


class StorageUnavailable(OSError):
    """Public-safe error; credentials and provider responses never escape."""


class Database:
    def __init__(self, settings, *, migration=False):
        self.settings, self.migration = settings, migration
        self._pool = None
        self._lock = threading.Lock()

    def _open(self):
        with self._lock:
            if self._pool is None:
                from psycopg_pool import ConnectionPool
                url = (self.settings.supabase_migration_database_url if self.migration
                       else self.settings.database_url).get_secret_value()
                certificate = self.settings.database_ssl_root_cert
                if not url or not certificate or not Path(certificate).is_file():
                    raise StorageUnavailable("Configure the database URL and Supabase CA certificate.")
                self._pool = ConnectionPool(url, min_size=0, max_size=self.settings.database_pool_size,
                    open=True, timeout=10, kwargs={"sslmode": "verify-full", "sslrootcert": str(certificate),
                    "connect_timeout": 10, "prepare_threshold": None, "options": "-c statement_timeout=30000"})
        return self._pool

    @contextmanager
    def connection(self):
        import psycopg
        from psycopg_pool import PoolTimeout
        try:
            with self._open().connection() as connection:
                if not self.migration:
                    user=connection.execute('SELECT current_user').fetchone()[0]
                    if user in {'postgres','supabase_admin'}:
                        raise StorageUnavailable('Use a restricted SpectraPlan runtime database login.')
                    connection.commit()
                yield connection
        except (psycopg.Error, PoolTimeout) as error:
            raise StorageUnavailable("Supabase database is unavailable. Check configuration and connectivity.") from None

    def close(self):
        if self._pool is not None:
            self._pool.close()


def json_value(value):
    from psycopg.types.json import Jsonb
    return Jsonb(value)
