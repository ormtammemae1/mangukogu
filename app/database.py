import os
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine, select

DATA_DIR = Path(os.getenv("MANGUKOGU_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
IMAGE_DIR = DATA_DIR / "images"
DATABASE_URL = os.getenv("MANGUKOGU_DB_URL", f"sqlite:///{DATA_DIR / 'mangukogu.db'}")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


@event.listens_for(engine, "connect")
def _enable_foreign_keys(dbapi_conn, _):
    # SQLite ignores ON DELETE CASCADE unless this is switched on per connection.
    dbapi_conn.execute("PRAGMA foreign_keys=ON")


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

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    IMAGE_DIR.mkdir(exist_ok=True)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        if session.exec(select(Category)).first() is None:
            for i, name in enumerate(DEFAULT_CATEGORIES):
                session.add(Category(name=name, position=i))
            session.commit()


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
