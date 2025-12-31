"""
Agent Registry - Single source of truth for agent configuration.

Loads agents.yaml and provides:
- Agent discovery
- Tool permissions
- Configuration lookup

No more hardcoded elif chains in api.py!
"""
import yaml
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

logger = logging.getLogger("agent-registry")


@dataclass
class AgentConfig:
    """Configuration for a single agent."""
    name: str
    description: str
    cwd: str
    tools: List[str]
    max_turns: int = 50
    timeout_seconds: int = 300
    model: str = "claude-sonnet-4-20250514"
    schedule: Optional[str] = None
    enabled: bool = True

    @property
    def allowed_tools(self) -> str:
        """Get comma-separated tool pattern for SDK."""
        return ",".join(self.tools)

    @property
    def tools_list(self) -> List[str]:
        """Get tools as list for SDK options."""
        return self.tools


@dataclass
class EndpointConfig:
    """Configuration for a simple API endpoint (non-agent)."""
    name: str
    description: str
    path: str
    tools: List[str] = field(default_factory=list)
    enabled: bool = True

    @property
    def allowed_tools(self) -> str:
        return ",".join(self.tools) if self.tools else ""


class AgentRegistry:
    """
    Registry for all agents and endpoints.

    Usage:
        registry = AgentRegistry()

        # Get agent config
        agent = registry.get_agent("feed-publisher")
        if agent:
            print(agent.allowed_tools)

        # List all agents
        for name in registry.list_agents():
            print(name)
    """

    def __init__(self, config_path: Optional[str] = None):
        """Initialize registry from config file."""
        if config_path is None:
            # Default config path
            config_path = Path(__file__).parent / "config" / "agents.yaml"
        else:
            config_path = Path(config_path)

        self._agents: Dict[str, AgentConfig] = {}
        self._endpoints: Dict[str, EndpointConfig] = {}
        self._defaults: Dict[str, Any] = {}

        self._load_config(config_path)

    def _load_config(self, config_path: Path) -> None:
        """Load configuration from YAML file."""
        if not config_path.exists():
            logger.warning(f"Config not found: {config_path}, using empty config")
            return

        try:
            with open(config_path) as f:
                config = yaml.safe_load(f)

            if not config:
                logger.warning("Empty config file")
                return

            # Load defaults
            self._defaults = config.get("defaults", {})

            # Load agents
            for name, agent_config in config.get("agents", {}).items():
                self._agents[name] = AgentConfig(
                    name=name,
                    description=agent_config.get("description", ""),
                    cwd=agent_config.get("cwd", "/app"),
                    tools=agent_config.get("tools", ["*"]),
                    max_turns=agent_config.get("max_turns", self._defaults.get("max_turns", 50)),
                    timeout_seconds=agent_config.get("timeout_seconds", self._defaults.get("timeout_seconds", 300)),
                    model=agent_config.get("model", self._defaults.get("model", "claude-sonnet-4-20250514")),
                    schedule=agent_config.get("schedule"),
                    enabled=agent_config.get("enabled", True)
                )

            # Load endpoints
            for name, endpoint_config in config.get("endpoints", {}).items():
                self._endpoints[name] = EndpointConfig(
                    name=name,
                    description=endpoint_config.get("description", ""),
                    path=endpoint_config.get("path", f"/api/{name}"),
                    tools=endpoint_config.get("tools", []),
                    enabled=endpoint_config.get("enabled", True)
                )

            logger.info(f"Loaded {len(self._agents)} agents and {len(self._endpoints)} endpoints")

        except yaml.YAMLError as e:
            logger.error(f"YAML parse error: {e}")
        except Exception as e:
            logger.error(f"Config load error: {e}")

    def get_agent(self, name: str) -> Optional[AgentConfig]:
        """Get agent configuration by name."""
        return self._agents.get(name)

    def get_endpoint(self, name: str) -> Optional[EndpointConfig]:
        """Get endpoint configuration by name."""
        return self._endpoints.get(name)

    def list_agents(self, enabled_only: bool = True) -> List[str]:
        """List all registered agent names."""
        if enabled_only:
            return [name for name, agent in self._agents.items() if agent.enabled]
        return list(self._agents.keys())

    def list_endpoints(self, enabled_only: bool = True) -> List[str]:
        """List all registered endpoint names."""
        if enabled_only:
            return [name for name, ep in self._endpoints.items() if ep.enabled]
        return list(self._endpoints.keys())

    def get_allowed_tools(self, agent_name: str) -> str:
        """Get allowed tools pattern for an agent.

        Returns comma-separated tool patterns, or "*" for full access.
        """
        agent = self.get_agent(agent_name)
        if agent:
            return agent.allowed_tools
        return "*"  # Default: full access for unknown agents

    def get_agent_cwd(self, agent_name: str) -> str:
        """Get working directory for an agent."""
        agent = self.get_agent(agent_name)
        if agent:
            return agent.cwd
        return "/app"

    def agent_exists(self, name: str) -> bool:
        """Check if an agent is registered."""
        return name in self._agents

    def get_all_agents(self) -> Dict[str, AgentConfig]:
        """Get all agent configurations."""
        return self._agents.copy()

    def get_defaults(self) -> Dict[str, Any]:
        """Get default settings."""
        return self._defaults.copy()

    def reload(self, config_path: Optional[str] = None) -> None:
        """Reload configuration from file."""
        if config_path:
            self._load_config(Path(config_path))
        else:
            self._load_config(Path(__file__).parent / "config" / "agents.yaml")
        logger.info("Configuration reloaded")


# Singleton instance for easy import
_registry: Optional[AgentRegistry] = None


def get_registry() -> AgentRegistry:
    """Get the global agent registry instance."""
    global _registry
    if _registry is None:
        _registry = AgentRegistry()
    return _registry


def reload_registry() -> None:
    """Reload the global registry from config file."""
    global _registry
    if _registry:
        _registry.reload()
    else:
        _registry = AgentRegistry()
