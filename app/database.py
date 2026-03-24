"""GliceMia database — SQLCipher encrypted SQLite with WAL mode."""

import logging

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, Session

from app.config import settings
from app.models import Base

log = logging.getLogger(__name__)

_engine = None
_SessionLocal = None


def _set_pragmas(dbapi_conn, connection_record):
    """Set SQLCipher key and performance pragmas on every raw connection."""
    cursor = dbapi_conn.cursor()
    if settings.DB_PASSPHRASE:
        # Use hex-encoded key to avoid SQL injection via passphrase content.
        # SQLCipher accepts PRAGMA key="x'hex'" for raw key bytes.
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
        db_url = f"sqlite:///{settings.DB_PATH}"
        _engine = create_engine(db_url, echo=False)
        event.listen(_engine, "connect", _set_pragmas)
        log.info("Database engine created: %s", settings.DB_PATH)
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
