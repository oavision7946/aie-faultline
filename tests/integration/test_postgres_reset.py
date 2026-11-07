"""Checks run after a database reset: extensions, schema and seed data are in place."""

from __future__ import annotations

from collections.abc import Iterator

import psycopg
import pytest

from faultline_core.config import AppSettings, SecretStore

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def conn(settings: AppSettings, secrets: SecretStore) -> Iterator[psycopg.Connection]:
    pg = settings.postgres
    found = secrets.require_all([pg.user_env, pg.password_env])
    with psycopg.connect(
        host=pg.host,
        port=pg.port,
        dbname=pg.database,
        user=found[pg.user_env].get_secret_value(),
        password=found[pg.password_env].get_secret_value(),
        connect_timeout=10,
    ) as connection:
        yield connection


def scalar(conn: psycopg.Connection, sql: str) -> object:
    row = conn.execute(sql).fetchone()
    assert row is not None
    return row[0]


def test_pgvector_enabled(conn: psycopg.Connection) -> None:
    assert scalar(conn, "select count(*) from pg_extension where extname = 'vector'") == 1
    distance = scalar(conn, "select '[1,0]'::extensions.vector <-> '[0,0]'::extensions.vector")
    assert distance == 1.0


def test_registry_seeded(conn: psycopg.Connection) -> None:
    ids = [r[0] for r in conn.execute("select dataset_id from public.datasets order by 1")]
    assert ids == ["hdfs-v1", "loghub-2k"]


def test_registry_rejects_bad_ids(conn: psycopg.Connection) -> None:
    with pytest.raises(psycopg.errors.CheckViolation), conn.transaction():
        conn.execute(
            "insert into public.datasets (dataset_id, name, source_url, license) "
            "values ('Bad Id', 'x', 'x', 'x')"
        )
