from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from emporio_agent.agent.tools import ToolContext, ToolRegistry, build_tools
from emporio_agent.clock import STORE_TZ, FixedClock
from emporio_agent.config import CATALOG_DB, DATA_DIR, POLICIES_JSON
from emporio_agent.ingest.pipeline import prepare
from emporio_agent.repositories.catalog import CatalogRepository
from emporio_agent.repositories.conversations import ConversationRepository
from emporio_agent.repositories.db import connect_catalog, connect_writable
from emporio_agent.repositories.orders import OrderRepository
from emporio_agent.services.catalog import CatalogService
from emporio_agent.services.orders import OrderService
from emporio_agent.services.policies import PolicyService

# Fixed "today" for every time-dependent test: the day the project started.
TODAY = date(2026, 10, 31)
NOW = datetime(2026, 10, 31, 10, 0, tzinfo=STORE_TZ)


@pytest.fixture(scope="session")
def var_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Generated store built from the real, original data files."""
    out = tmp_path_factory.mktemp("var")
    report = prepare(DATA_DIR, out, apply=True, reference_date=TODAY)
    assert report.applied and not report.errors
    return out


@pytest.fixture(scope="session")
def catalog_conn(var_dir: Path):
    conn = connect_catalog(var_dir / CATALOG_DB)
    yield conn
    conn.close()


@pytest.fixture(scope="session")
def catalog(catalog_conn) -> CatalogService:
    return CatalogService(CatalogRepository(catalog_conn))


@pytest.fixture(scope="session")
def orders(catalog_conn) -> OrderService:
    return OrderService(OrderRepository(catalog_conn))


@pytest.fixture(scope="session")
def policies(var_dir: Path) -> PolicyService:
    return PolicyService(var_dir / POLICIES_JSON)


@pytest.fixture
def conversations(tmp_path: Path) -> ConversationRepository:
    return ConversationRepository(connect_writable(tmp_path / "conversations.db"))


@pytest.fixture
def tools(catalog, orders, policies, conversations) -> ToolRegistry:
    ctx = ToolContext(catalog, orders, policies, conversations, FixedClock(NOW), "test-session")
    return build_tools(ctx)
