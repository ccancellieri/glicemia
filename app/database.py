"""GliceMia database — SQLCipher encrypted SQLite with WAL mode.

Uses sqlcipher3 DBAPI when available (encrypted at rest).
Falls back to standard sqlite3 (unencrypted) for local development.
"""

import logging

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, Session

from app.config import settings
from app.models import Base

log = logging.getLogger(__name__)

_engine = None
_SessionLocal = None
_use_sqlcipher = False

# Try to import sqlcipher3 as the DBAPI module
try:
    import sqlcipher3.dbapi2 as _sqlcipher_dbapi
    _use_sqlcipher = True
except ImportError:
    _sqlcipher_dbapi = None


def _sqlcipher_creator():
    """Create a raw sqlcipher3 connection to the DB file."""
    return _sqlcipher_dbapi.connect(str(settings.DB_PATH))


def _set_pragmas(dbapi_conn, connection_record):
    """Set SQLCipher key and performance pragmas on every raw connection."""
    cursor = dbapi_conn.cursor()
    if _use_sqlcipher and settings.DB_PASSPHRASE:
        # SQLCipher: set encryption key before any other operation.
        hex_key = settings.DB_PASSPHRASE.encode().hex()
        cursor.execute(f"PRAGMA key=\"x'{hex_key}'\";")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=normal")
    cursor.execute("PRAGMA temp_store=memory")
    cursor.execute("PRAGMA mmap_size=268435456")
    cursor.execute("PRAGMA cache_size=-64000")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def get_engine():
    global _engine
    if _engine is None:
        if _use_sqlcipher:
            # Use sqlcipher3 DBAPI with a custom creator
            _engine = create_engine("sqlite://", creator=_sqlcipher_creator, echo=False)
            log.info("Database engine created (SQLCipher): %s", settings.DB_PATH)
        else:
            db_url = f"sqlite:///{settings.DB_PATH}"
            _engine = create_engine(db_url, echo=False)
            log.info("Database engine created (standard SQLite): %s", settings.DB_PATH)
        event.listen(_engine, "connect", _set_pragmas)
    return _engine


def get_session() -> Session:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine())
    return _SessionLocal()


def init_db():
    """Create all tables if they don't exist."""
    engine = get_engine()
    Base.metadata.create_all(engine)
    log.info("Database tables initialized")
