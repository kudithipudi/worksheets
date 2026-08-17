"""
Database engine, session factory, and initialisation helpers.
WAL mode is enabled for improved concurrent-read performance with SQLite.
"""

from datetime import datetime, timedelta

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.models.orm import Base, RateLimitHit

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
    echo=False,
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
    """Apply performance and safety pragmas on every new SQLite connection."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA cache_size=-32000")   # ~32 MB page cache
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """Create all tables if they do not already exist."""
    Base.metadata.create_all(bind=engine)


def migrate_db() -> None:
    """
    Forward-only migrations for columns added after initial deployment.
    SQLite does not support IF NOT EXISTS on ALTER TABLE, so we swallow
    the OperationalError that fires when a column already exists.
    """
    migrations = [
        "ALTER TABLE questions ADD COLUMN topic VARCHAR(100) NOT NULL DEFAULT 'General'",
        "ALTER TABLE questions ADD COLUMN level VARCHAR(20)  NOT NULL DEFAULT 'On-Level'",
        "ALTER TABLE questions ADD COLUMN teks_code VARCHAR(50) NOT NULL DEFAULT ''",
        "ALTER TABLE questions ADD COLUMN flag_reason VARCHAR(100) NOT NULL DEFAULT ''",
    ]
    with engine.connect() as conn:
        for stmt in migrations:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                pass  # column already present — safe to ignore


def get_db():
    """FastAPI dependency: yields a database session and closes it afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_and_record_rate_limit(
    session: Session,
    *,
    ip: str,
    route: str,
    limit: int,
    window_seconds: int,
) -> bool:
    """Record a hit for (ip, route) and return whether it's within `limit`
    hits in the trailing `window_seconds`. Also prunes hits for this route
    older than the window, so the table doesn't grow unbounded."""
    cutoff = datetime.utcnow() - timedelta(seconds=window_seconds)
    session.query(RateLimitHit).filter(
        RateLimitHit.route == route,
        RateLimitHit.created_at < cutoff,
    ).delete(synchronize_session=False)
    count = (
        session.query(RateLimitHit)
        .filter(
            RateLimitHit.route == route,
            RateLimitHit.ip == ip,
            RateLimitHit.created_at >= cutoff,
        )
        .count()
    )
    if count >= limit:
        session.commit()
        return False
    session.add(RateLimitHit(ip=ip, route=route))
    session.commit()
    return True
