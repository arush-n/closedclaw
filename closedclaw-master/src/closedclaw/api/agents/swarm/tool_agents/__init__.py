"""Per-tool specialized agents for the Openclaw swarm."""

from closedclaw.api.agents.swarm.tool_agents.web_search import WebSearchAgent
from closedclaw.api.agents.swarm.tool_agents.code_executor import CodeExecutorAgent
from closedclaw.api.agents.swarm.tool_agents.file_access import FileAccessAgent
from closedclaw.api.agents.swarm.tool_agents.calendar import CalendarAgent
from closedclaw.api.agents.swarm.tool_agents.email import EmailAgent
from closedclaw.api.agents.swarm.tool_agents.browser import BrowserAgent
from closedclaw.api.agents.swarm.tool_agents.notification import NotificationAgent
from closedclaw.api.agents.swarm.tool_agents.tool_orchestrator import ToolOrchestratorAgent
from closedclaw.api.agents.swarm.tool_agents.gmail_agent import GmailAgent
from closedclaw.api.agents.swarm.tool_agents.notion_agent import NotionAgent
from closedclaw.api.agents.swarm.tool_agents.drive_agent import DriveAgent
from closedclaw.api.agents.swarm.tool_agents.slack_agent import SlackAgent
from closedclaw.api.agents.swarm.tool_agents.github_agent import GitHubToolAgent

TOOL_AGENT_CLASSES = {
    "web_search": WebSearchAgent,
    "code_executor": CodeExecutorAgent,
    "file_access": FileAccessAgent,
    "calendar": CalendarAgent,
    "email": EmailAgent,
    "browser": BrowserAgent,
    "notification": NotificationAgent,
    "tool_orchestrator": ToolOrchestratorAgent,
    "gmail": GmailAgent,
    "notion": NotionAgent,
    "drive": DriveAgent,
    "slack": SlackAgent,
    "github_tool": GitHubToolAgent,
}

__all__ = [
    "WebSearchAgent",
    "CodeExecutorAgent",
    "FileAccessAgent",
    "CalendarAgent",
    "EmailAgent",
    "BrowserAgent",
    "NotificationAgent",
    "ToolOrchestratorAgent",
    "GmailAgent",
    "NotionAgent",
    "DriveAgent",
    "SlackAgent",
    "GitHubToolAgent",
    "TOOL_AGENT_CLASSES",
]
