import os
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine, select

from .images import BLOB_ENABLED

DATA_DIR = Path(os.getenv("MANGUKOGU_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
IMAGE_DIR = DATA_DIR / "images"


def _database_url() -> str:
    # On Vercel the Neon/Postgres integration sets DATABASE_URL; locally and on the Pi it's a SQLite file.
    url = os.getenv("MANGUKOGU_DB_URL") or os.getenv("DATABASE_URL")
    if not url:
        return f"sqlite:///{DATA_DIR / 'mangukogu.db'}"
    # Hosted Postgres hands out postgres:// URLs; SQLAlchemy needs the driver named.
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


DATABASE_URL = _database_url()
IS_SQLITE = DATABASE_URL.startswith("sqlite")

if IS_SQLITE:
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_conn, _):
        # SQLite ignores ON DELETE CASCADE unless this is switched on per connection.
        dbapi_conn.execute("PRAGMA foreign_keys=ON")
else:
    # Serverless instances sit idle between requests; drop connections the server has closed.
    engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=300)


# The categories the teacher already uses; added once, when the database is new.
DEFAULT_CATEGORIES = [
    "Tähelepanu ja keskendumine",
    "Peenmotoorika",
    "Töömälu",
    "Arvu- ja hulgataju",
    "Silma ja käe koostöö",
    "Suurustaju",
    "Terviktaju",
    "Jutustamisoskus",
    "Sotsiaalsed oskused",
    "Koostöö",
    "Eesti keele õpe",
    "Esi- ja lõpuhääliku määramine",
    "Foneemi kuulmine",
    "Sorteerimine",
    "Rühmitamine",
    "Loogika",
    "Juhiste järgi tegutsemine",
]


def init_db() -> None:
    from .models import Category

    if os.getenv("VERCEL") and (IS_SQLITE or not BLOB_ENABLED):
        # Vercel's disk is read-only and wiped between instances, so local files would be lost.
        raise RuntimeError(
            "On Vercel, connect a Postgres database (DATABASE_URL) and a Blob store (BLOB_READ_WRITE_TOKEN)."
        )
    if IS_SQLITE:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not BLOB_ENABLED:
        IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        if session.exec(select(Category)).first() is None:
            for i, name in enumerate(DEFAULT_CATEGORIES):
                session.add(Category(name=name, position=i))
            session.commit()


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
