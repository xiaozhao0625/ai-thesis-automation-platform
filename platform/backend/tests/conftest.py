from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker


TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://postgres@127.0.0.1:55432/thesis_p1_1",
)


@pytest.fixture(scope="session")
def postgres_engine():
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    command.upgrade(Config("alembic.ini"), "head")
    engine = create_engine(TEST_DATABASE_URL)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(postgres_engine) -> Iterator[Session]:
    factory = sessionmaker(bind=postgres_engine, expire_on_commit=False)
    with postgres_engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE TABLE tasks, outbox_events, worker_instances "
                "RESTART IDENTITY CASCADE"
            )
        )
    with factory() as session:
        yield session
        session.rollback()
