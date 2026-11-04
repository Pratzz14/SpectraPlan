"""Provision a restricted runtime login without exposing its generated password."""
from urllib.parse import urlsplit,urlunsplit,quote
import secrets
from backend.core.config import PROJECT_ROOT


def create_runtime_login(settings,database):
    from psycopg import sql
    if settings.database_url.get_secret_value():
        raise ValueError('DATABASE_URL already exists; refusing to replace runtime credentials')
    password=secrets.token_urlsafe(32)
    role='spectraplan_app'
    parsed=urlsplit(settings.supabase_migration_database_url.get_secret_value())
    if not parsed.hostname:
        raise ValueError('Configure the migration database URL')
    # Supavisor usernames carry the project reference after the role name.
    suffix='.'+parsed.username.split('.',1)[1] if '.' in (parsed.username or '') else ''
    user=role+suffix
    host=parsed.hostname
    if ':' in host:
        host='['+host+']'
    netloc=quote(user,safe='.')+':'+quote(password,safe='')+'@'+host+(':'+str(parsed.port) if parsed.port else '')
    url=urlunsplit((parsed.scheme,netloc,parsed.path,parsed.query,''))
    env=PROJECT_ROOT/'.env'
    original=env.read_text(encoding='utf-8') if env.is_file() else ''
    # Never create an unrecorded password: require writable local configuration first.
    if env.exists() and not __import__('os').access(env,__import__('os').W_OK):
        raise ValueError('Local .env is not writable')
    with database.connection() as c:
        if c.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(role,)).fetchone():
            raise ValueError('Runtime role already exists; configure its existing credentials manually')
        c.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {} IN ROLE spectraplan_backend').format(sql.Identifier(role),sql.Literal(password)))
    import re
    text=re.sub(r'(?m)^DATABASE_URL=.*(?:\r?\n|$)','',original)
    env.write_text(text.rstrip()+'\nDATABASE_URL='+url+'\n',encoding='utf-8')
