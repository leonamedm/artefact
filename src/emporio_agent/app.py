"""Composition root: wires repositories, services, tools and the agent."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from emporio_agent.agent.llm import ChatModel
from emporio_agent.agent.loop import Agent
from emporio_agent.agent.tools import ToolContext, ToolRegistry, build_tools
from emporio_agent.clock import Clock
from emporio_agent.config import CATALOG_DB, CONVERSATIONS_DB, POLICIES_JSON
from emporio_agent.repositories.catalog import CatalogRepository
from emporio_agent.repositories.conversations import ConversationRepository
from emporio_agent.repositories.db import connect_catalog, connect_writable
from emporio_agent.repositories.orders import OrderRepository
from emporio_agent.services.catalog import CatalogService
from emporio_agent.services.orders import OrderService
from emporio_agent.services.policies import PolicyService


@dataclass
class Application:
    agent: Agent
    tools: ToolRegistry
    context: ToolContext
    conversations: ConversationRepository | None


def build_application(
    var_dir: Path,
    model: ChatModel,
    clock: Clock,
    *,
    persist_conversations: bool = True,
) -> Application:
    catalog_conn = connect_catalog(var_dir / CATALOG_DB)
    conversations = (
        ConversationRepository(connect_writable(var_dir / CONVERSATIONS_DB))
        if persist_conversations
        else None
    )
    context = ToolContext(
        catalog=CatalogService(CatalogRepository(catalog_conn)),
        orders=OrderService(OrderRepository(catalog_conn)),
        policies=PolicyService(var_dir / POLICIES_JSON),
        conversations=conversations,
        clock=clock,
    )
    tools = build_tools(context)
    return Application(Agent(model, tools, clock), tools, context, conversations)
