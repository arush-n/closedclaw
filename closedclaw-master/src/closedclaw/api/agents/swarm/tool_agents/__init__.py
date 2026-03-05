"""Per-tool specialized agents for the Openclaw swarm."""

from closedclaw.api.agents.swarm.tool_agents.web_search import WebSearchAgent
from closedclaw.api.agents.swarm.tool_agents.code_executor import CodeExecutorAgent
from closedclaw.api.agents.swarm.tool_agents.file_access import FileAccessAgent
from closedclaw.api.agents.swarm.tool_agents.calendar import CalendarAgent
from closedclaw.api.agents.swarm.tool_agents.email import EmailAgent
from closedclaw.api.agents.swarm.tool_agents.browser import BrowserAgent
from closedclaw.api.agents.swarm.tool_agents.notification import NotificationAgent

TOOL_AGENT_CLASSES = {
    "web_search": WebSearchAgent,
    "code_executor": CodeExecutorAgent,
    "file_access": FileAccessAgent,
    "calendar": CalendarAgent,
    "email": EmailAgent,
    "browser": BrowserAgent,
    "notification": NotificationAgent,
}

__all__ = [
    "WebSearchAgent",
    "CodeExecutorAgent",
    "FileAccessAgent",
    "CalendarAgent",
    "EmailAgent",
    "BrowserAgent",
    "NotificationAgent",
    "TOOL_AGENT_CLASSES",
]
