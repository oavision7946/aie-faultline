"""The ClickHouse writer can write; the read-only user cannot, and its limits apply."""

from __future__ import annotations

import urllib.error
import urllib.request
from dataclasses import dataclass

import pytest

from faultline_core.config import AppSettings, SecretStore

pytestmark = pytest.mark.integration


@dataclass
class Reply:
    status: int
    body: str


@dataclass
class Client:
    url: str
    user: str | None
    password: str | None

    def query(self, sql: str) -> Reply:
        request = urllib.request.Request(self.url, data=sql.encode(), method="POST")
        if self.user is not None and self.password is not None:
            request.add_header("X-ClickHouse-User", self.user)
            request.add_header("X-ClickHouse-Key", self.password)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return Reply(response.status, response.read().decode())
        except urllib.error.HTTPError as exc:
            return Reply(exc.code, exc.read().decode())


@pytest.fixture(scope="module")
def clients(settings: AppSettings, secrets: SecretStore) -> dict[str, Client]:
    ch = settings.clickhouse
    url = f"http://{ch.host}:{ch.http_port}/"
    found = secrets.require_all([ch.writer_password_env, ch.readonly_password_env])
    writer = Client(url, ch.writer_user, found[ch.writer_password_env].get_secret_value())
    reader = Client(url, ch.readonly_user, found[ch.readonly_password_env].get_secret_value())
    table = f"{ch.database}.integration_probe"
    setup = [
        f"CREATE TABLE IF NOT EXISTS {table} (x UInt32) ENGINE = MergeTree ORDER BY x",
        f"TRUNCATE TABLE {table}",
        f"INSERT INTO {table} VALUES (1), (2), (3)",
    ]
    for sql in setup:
        reply = writer.query(sql)
        assert reply.status == 200, reply.body
    return {"writer": writer, "reader": reader, "anonymous": Client(url, None, None),
            "table": Client(table, None, None)}  # fmt: skip


def table(clients: dict[str, Client]) -> str:
    return clients["table"].url


def test_reader_can_select(clients: dict[str, Client]) -> None:
    reply = clients["reader"].query(f"SELECT count() FROM {table(clients)}")
    assert (reply.status, reply.body.strip()) == (200, "3")


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO {t} VALUES (4)",
        "ALTER TABLE {t} DELETE WHERE x = 1",
        "TRUNCATE TABLE {t}",
        "DROP TABLE {t}",
        "CREATE TABLE {t}_new (x UInt8) ENGINE = Memory",
    ],
)
def test_reader_cannot_write(clients: dict[str, Client], sql: str) -> None:
    reply = clients["reader"].query(sql.format(t=table(clients)))
    assert reply.status != 200
    assert "READONLY" in reply.body or "readonly" in reply.body
    count = clients["writer"].query(f"SELECT count() FROM {table(clients)}")
    assert count.body.strip() == "3"


def test_reader_cannot_lift_its_limits(clients: dict[str, Client]) -> None:
    reply = clients["reader"].query("SELECT 1 SETTINGS readonly = 0")
    assert reply.status != 200


def test_reader_result_limit_enforced(clients: dict[str, Client], settings: AppSettings) -> None:
    rows = settings.clickhouse.readonly_limits.max_result_rows + 1
    reply = clients["reader"].query(f"SELECT number FROM numbers({rows})")
    assert reply.status != 200
    assert "TOO_MANY_ROWS_OR_BYTES" in reply.body


def test_anonymous_access_denied(clients: dict[str, Client]) -> None:
    reply = clients["anonymous"].query("SELECT 1")
    assert reply.status in (401, 403, 516)
