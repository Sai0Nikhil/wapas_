from collections.abc import Iterator

from sqlmodel import Session, SQLModel, create_engine

from app.config import get_settings

settings = get_settings()
_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=_args)


def init_db() -> None:
    from app import models  # noqa: F401  (registers tables)

    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
