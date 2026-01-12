#!/usr/bin/env python3
"""
Unified Coolify MCP Server - Manages MULTIPLE Coolify instances

Supports two Coolify servers:
- "faric" (46.224.117.155) - THIS SERVER (where Claude Code is running)
- "hetzner" (91.98.235.81) - Remote Hetzner server

Every tool accepts a `server` parameter to choose which instance to use.
Default is "faric" (current server).

Provides full access to Coolify API for managing:
- Applications (create, update, delete, start, stop, restart, logs, env vars)
- Databases (PostgreSQL, MySQL, MariaDB, MongoDB, Redis, KeyDB, DragonFly, ClickHouse)
- Services (one-click services with full lifecycle management)
- Servers (list, validate, resources, domains)
- Projects & Environments
- Deployments (trigger, monitor, list)
- Teams & Private Keys

Author: Claude Code
Version: 2.0.0 - Unified multi-server support
"""

import os
import json
import logging
from typing import Any, Optional, Literal
from datetime import datetime
import httpx
from mcp.server.fastmcp import FastMCP

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("coolify-mcp")

# Initialize FastMCP server
mcp = FastMCP("coolify")

# =============================================================================
# SERVER CONFIGURATIONS
# =============================================================================

SERVERS = {
    "faric": {
        "name": "Faric Server (THIS SERVER)",
        "url": os.getenv("COOLIFY_FARIC_URL", "http://46.224.117.155:8000"),
        "token": os.getenv("COOLIFY_FARIC_TOKEN", "8|skhubBnCoPY6G1ccBmosO0MkwIQKmCjDzALEou4S46cc458d"),
        "description": "THIS SERVER - Claude Code runs here (46.224.117.155)"
    },
    "hetzner": {
        "name": "Hetzner Server (Remote)",
        "url": os.getenv("COOLIFY_HETZNER_URL", "http://91.98.235.81:8000"),
        "token": os.getenv("COOLIFY_HETZNER_TOKEN", "ZhaCxpWQM6hbkzlQKOmwrkC8h0nqKkeDLJvsyR1513087aeb"),
        "description": "Remote Hetzner server (91.98.235.81)"
    }
}

DEFAULT_SERVER = "faric"

# Type alias for server selection
ServerType = Literal["hetzner", "faric"]


def get_server_config(server: str = DEFAULT_SERVER) -> dict:
    """Get configuration for the specified server"""
    if server not in SERVERS:
        raise ValueError(f"Unknown server '{server}'. Available: {list(SERVERS.keys())}")
    return SERVERS[server]


def get_client(server: str = DEFAULT_SERVER) -> httpx.Client:
    """Get HTTP client configured for the specified server"""
    config = get_server_config(server)
    return httpx.Client(
        headers={
            "Authorization": f"Bearer {config['token']}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        },
        timeout=60.0
    )


def api_request(method: str, endpoint: str, server: str = DEFAULT_SERVER, data: dict = None, params: dict = None) -> dict:
    """Make API request to specified Coolify server"""
    config = get_server_config(server)
    url = f"{config['url']}/api/v1{endpoint}"

    with get_client(server) as client:
        try:
            if method == "GET":
                response = client.get(url, params=params)
            elif method == "POST":
                response = client.post(url, json=data)
            elif method == "PATCH":
                response = client.patch(url, json=data)
            elif method == "PUT":
                response = client.put(url, json=data)
            elif method == "DELETE":
                response = client.delete(url)
            else:
                return {"error": f"Unsupported method: {method}"}

            if response.status_code >= 400:
                return {
                    "error": True,
                    "server": server,
                    "status_code": response.status_code,
                    "message": response.text
                }

            # Handle empty responses
            if not response.text:
                return {"success": True, "server": server, "status_code": response.status_code}

            result = response.json()
            # Add server info to response for clarity
            if isinstance(result, dict):
                result["_server"] = server
            return result

        except Exception as e:
            logger.error(f"API request failed on {server}: {e}")
            return {"error": str(e), "server": server}


# ============================================================================
# META TOOLS - Server Information
# ============================================================================

@mcp.tool()
def list_coolify_servers() -> str:
    """List all configured Coolify server instances and their status

    Returns information about available servers (hetzner, faric) and tests connectivity.
    """
    result = {
        "servers": [],
        "default": DEFAULT_SERVER
    }

    for server_id, config in SERVERS.items():
        server_info = {
            "id": server_id,
            "name": config["name"],
            "url": config["url"],
            "description": config["description"],
            "status": "unknown"
        }

        # Test connectivity
        try:
            health = api_request("GET", "/healthcheck", server=server_id)
            if "error" not in health:
                server_info["status"] = "healthy"
            else:
                server_info["status"] = "error"
                server_info["error"] = health.get("message", str(health))
        except Exception as e:
            server_info["status"] = "unreachable"
            server_info["error"] = str(e)

        result["servers"].append(server_info)

    return json.dumps(result, indent=2)


# ============================================================================
# SYSTEM TOOLS
# ============================================================================

@mcp.tool()
def get_version(server: str = DEFAULT_SERVER) -> str:
    """Get Coolify API version

    Args:
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    result = api_request("GET", "/version", server=server)
    return json.dumps(result, indent=2)


@mcp.tool()
def healthcheck(server: str = DEFAULT_SERVER) -> str:
    """Check Coolify API health status

    Args:
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    result = api_request("GET", "/healthcheck", server=server)
    return json.dumps(result, indent=2)


# ============================================================================
# SERVER TOOLS
# ============================================================================

@mcp.tool()
def list_servers(server: str = DEFAULT_SERVER) -> str:
    """List all servers managed by this Coolify instance

    Args:
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    result = api_request("GET", "/servers", server=server)
    return json.dumps(result, indent=2)


@mcp.tool()
def get_server(uuid: str, server: str = DEFAULT_SERVER) -> str:
    """Get detailed information about a specific server

    Args:
        uuid: Server UUID
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    result = api_request("GET", f"/servers/{uuid}", server=server)
    return json.dumps(result, indent=2)


@mcp.tool()
def get_server_resources(uuid: str, server: str = DEFAULT_SERVER) -> str:
    """Get all resources (applications, databases, services) on a server

    Args:
        uuid: Server UUID
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    result = api_request("GET", f"/servers/{uuid}/resources", server=server)
    return json.dumps(result, indent=2)


@mcp.tool()
def get_server_domains(uuid: str, server: str = DEFAULT_SERVER) -> str:
    """Get all domains configured on a server

    Args:
        uuid: Server UUID
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    result = api_request("GET", f"/servers/{uuid}/domains", server=server)
    return json.dumps(result, indent=2)


@mcp.tool()
def validate_server(uuid: str, server: str = DEFAULT_SERVER) -> str:
    """Validate server connection and configuration

    Args:
        uuid: Server UUID
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    result = api_request("GET", f"/servers/{uuid}/validate", server=server)
    return json.dumps(result, indent=2)


# ============================================================================
# PROJECT TOOLS
# ============================================================================

@mcp.tool()
def list_projects(server: str = DEFAULT_SERVER) -> str:
    """List all projects

    Args:
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    result = api_request("GET", "/projects", server=server)
    return json.dumps(result, indent=2)


@mcp.tool()
def get_project(uuid: str, server: str = DEFAULT_SERVER) -> str:
    """Get project details including environments

    Args:
        uuid: Project UUID
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    result = api_request("GET", f"/projects/{uuid}", server=server)
    return json.dumps(result, indent=2)


@mcp.tool()
def create_project(name: str, description: str = "", server: str = DEFAULT_SERVER) -> str:
    """Create a new project

    Args:
        name: Project name
        description: Optional project description
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    data = {"name": name}
    if description:
        data["description"] = description
    result = api_request("POST", "/projects", server=server, data=data)
    return json.dumps(result, indent=2)


@mcp.tool()
def update_project(uuid: str, name: str = None, description: str = None, server: str = DEFAULT_SERVER) -> str:
    """Update project settings

    Args:
        uuid: Project UUID
        name: New project name (optional)
        description: New project description (optional)
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    data = {}
    if name:
        data["name"] = name
    if description:
        data["description"] = description
    result = api_request("PATCH", f"/projects/{uuid}", server=server, data=data)
    return json.dumps(result, indent=2)


@mcp.tool()
def delete_project(uuid: str, server: str = DEFAULT_SERVER) -> str:
    """Delete a project

    Args:
        uuid: Project UUID
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    result = api_request("DELETE", f"/projects/{uuid}", server=server)
    return json.dumps(result, indent=2)


# ============================================================================
# ENVIRONMENT TOOLS
# ============================================================================

@mcp.tool()
def list_environments(project_uuid: str, server: str = DEFAULT_SERVER) -> str:
    """List all environments in a project

    Args:
        project_uuid: Project UUID
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    result = api_request("GET", f"/projects/{project_uuid}", server=server)
    if isinstance(result, dict) and "environments" in result:
        return json.dumps(result["environments"], indent=2)
    return json.dumps(result, indent=2)


@mcp.tool()
def create_environment(project_uuid: str, name: str, description: str = "", server: str = DEFAULT_SERVER) -> str:
    """Create a new environment in a project

    Args:
        project_uuid: Project UUID
        name: Environment name
        description: Optional environment description
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    data = {"name": name}
    if description:
        data["description"] = description
    result = api_request("POST", f"/projects/{project_uuid}/environments", server=server, data=data)
    return json.dumps(result, indent=2)


@mcp.tool()
def delete_environment(project_uuid: str, environment_name: str, server: str = DEFAULT_SERVER) -> str:
    """Delete an environment from a project

    Args:
        project_uuid: Project UUID
        environment_name: Environment name to delete
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    result = api_request("DELETE", f"/projects/{project_uuid}/{environment_name}", server=server)
    return json.dumps(result, indent=2)


# ============================================================================
# APPLICATION TOOLS
# ============================================================================

@mcp.tool()
def list_applications(server: str = DEFAULT_SERVER) -> str:
    """List all applications

    Args:
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    result = api_request("GET", "/applications", server=server)
    return json.dumps(result, indent=2)


@mcp.tool()
def get_application(uuid: str, server: str = DEFAULT_SERVER) -> str:
    """Get detailed application information including environment variables

    Args:
        uuid: Application UUID
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    result = api_request("GET", f"/applications/{uuid}", server=server)
    return json.dumps(result, indent=2)


@mcp.tool()
def update_application(
    uuid: str,
    name: str = None,
    description: str = None,
    fqdn: str = None,
    git_branch: str = None,
    ports_exposes: str = None,
    health_check_enabled: bool = None,
    health_check_path: str = None,
    server: str = DEFAULT_SERVER
) -> str:
    """Update application configuration

    Args:
        uuid: Application UUID
        name: New application name
        description: Application description
        fqdn: Fully qualified domain name (comma-separated for multiple)
        git_branch: Git branch to deploy from
        ports_exposes: Ports to expose (comma-separated)
        health_check_enabled: Enable health checks
        health_check_path: Health check endpoint path
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    data = {}
    if name is not None:
        data["name"] = name
    if description is not None:
        data["description"] = description
    if fqdn is not None:
        data["fqdn"] = fqdn
    if git_branch is not None:
        data["git_branch"] = git_branch
    if ports_exposes is not None:
        data["ports_exposes"] = ports_exposes
    if health_check_enabled is not None:
        data["health_check_enabled"] = health_check_enabled
    if health_check_path is not None:
        data["health_check_path"] = health_check_path

    result = api_request("PATCH", f"/applications/{uuid}", server=server, data=data)
    return json.dumps(result, indent=2)


@mcp.tool()
def delete_application(
    uuid: str,
    delete_configurations: bool = True,
    delete_volumes: bool = False,
    docker_cleanup: bool = True,
    server: str = DEFAULT_SERVER
) -> str:
    """Delete an application

    Args:
        uuid: Application UUID
        delete_configurations: Delete configuration files
        delete_volumes: Delete associated volumes
        docker_cleanup: Clean up Docker resources
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    params = {
        "delete_configurations": delete_configurations,
        "delete_volumes": delete_volumes,
        "docker_cleanup": docker_cleanup
    }
    result = api_request("DELETE", f"/applications/{uuid}", server=server, params=params)
    return json.dumps(result, indent=2)


@mcp.tool()
def start_application(uuid: str, server: str = DEFAULT_SERVER) -> str:
    """Start an application

    Args:
        uuid: Application UUID
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    result = api_request("POST", f"/applications/{uuid}/start", server=server)
    return json.dumps(result, indent=2)


@mcp.tool()
def stop_application(uuid: str, server: str = DEFAULT_SERVER) -> str:
    """Stop an application

    Args:
        uuid: Application UUID
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    result = api_request("POST", f"/applications/{uuid}/stop", server=server)
    return json.dumps(result, indent=2)


@mcp.tool()
def restart_application(uuid: str, server: str = DEFAULT_SERVER) -> str:
    """Restart an application (triggers new deployment)

    Args:
        uuid: Application UUID
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    result = api_request("POST", f"/applications/{uuid}/restart", server=server)
    return json.dumps(result, indent=2)


@mcp.tool()
def get_application_logs(uuid: str, lines: int = 100, server: str = DEFAULT_SERVER) -> str:
    """Get application container logs

    Args:
        uuid: Application UUID
        lines: Number of log lines to retrieve (default: 100)
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    result = api_request("GET", f"/applications/{uuid}/logs", server=server, params={"lines": lines})
    return json.dumps(result, indent=2)


# ============================================================================
# APPLICATION ENVIRONMENT VARIABLES
# ============================================================================

@mcp.tool()
def list_app_envs(uuid: str, server: str = DEFAULT_SERVER) -> str:
    """List all environment variables for an application

    Args:
        uuid: Application UUID
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    result = api_request("GET", f"/applications/{uuid}/envs", server=server)
    return json.dumps(result, indent=2)


@mcp.tool()
def create_app_env(
    uuid: str,
    key: str,
    value: str,
    is_preview: bool = False,
    is_build_time: bool = False,
    is_literal: bool = True,
    server: str = DEFAULT_SERVER
) -> str:
    """Create an environment variable for an application

    Args:
        uuid: Application UUID
        key: Variable name
        value: Variable value
        is_preview: Available in preview deployments
        is_build_time: Available during build
        is_literal: Treat as literal value (not interpolated)
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    data = {
        "key": key,
        "value": value,
        "is_preview": is_preview,
        "is_build_time": is_build_time,
        "is_literal": is_literal
    }
    result = api_request("POST", f"/applications/{uuid}/envs", server=server, data=data)
    return json.dumps(result, indent=2)


@mcp.tool()
def update_app_env(env_uuid: str, key: str = None, value: str = None, server: str = DEFAULT_SERVER) -> str:
    """Update an environment variable

    Args:
        env_uuid: Environment variable UUID
        key: New variable name (optional)
        value: New variable value (optional)
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    data = {}
    if key is not None:
        data["key"] = key
    if value is not None:
        data["value"] = value
    result = api_request("PATCH", f"/applications/envs/{env_uuid}", server=server, data=data)
    return json.dumps(result, indent=2)


@mcp.tool()
def delete_app_env(uuid: str, env_uuid: str, server: str = DEFAULT_SERVER) -> str:
    """Delete an environment variable from an application

    Args:
        uuid: Application UUID
        env_uuid: Environment variable UUID
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    result = api_request("DELETE", f"/applications/{uuid}/envs/{env_uuid}", server=server)
    return json.dumps(result, indent=2)


@mcp.tool()
def bulk_update_app_envs(uuid: str, env_vars: list, server: str = DEFAULT_SERVER) -> str:
    """Bulk create or update environment variables

    Args:
        uuid: Application UUID
        env_vars: List of env var dicts with keys: key, value, is_preview, is_build_time
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    result = api_request("PATCH", f"/applications/{uuid}/envs/bulk", server=server, data={"data": env_vars})
    return json.dumps(result, indent=2)


# ============================================================================
# APPLICATION CREATION
# ============================================================================

@mcp.tool()
def create_application_public(
    project_uuid: str,
    server_uuid: str,
    environment_name: str,
    git_repository: str,
    git_branch: str = "main",
    build_pack: str = "nixpacks",
    ports_exposes: str = "3000",
    name: str = None,
    description: str = None,
    instant_deploy: bool = False,
    server: str = DEFAULT_SERVER
) -> str:
    """Create application from a public Git repository

    Args:
        project_uuid: Target project UUID
        server_uuid: Target server UUID (the server within Coolify to deploy to)
        environment_name: Environment name (e.g., 'production')
        git_repository: Public Git repository URL
        git_branch: Git branch (default: main)
        build_pack: Build pack (nixpacks, dockerfile, dockercompose, static)
        ports_exposes: Ports to expose (comma-separated)
        name: Application name
        description: Application description
        instant_deploy: Deploy immediately after creation
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    data = {
        "project_uuid": project_uuid,
        "server_uuid": server_uuid,
        "environment_name": environment_name,
        "git_repository": git_repository,
        "git_branch": git_branch,
        "build_pack": build_pack,
        "ports_exposes": ports_exposes,
        "instant_deploy": instant_deploy
    }
    if name:
        data["name"] = name
    if description:
        data["description"] = description

    result = api_request("POST", "/applications/public", server=server, data=data)
    return json.dumps(result, indent=2)


@mcp.tool()
def create_application_dockerfile(
    project_uuid: str,
    server_uuid: str,
    environment_name: str,
    git_repository: str,
    git_branch: str = "main",
    dockerfile_location: str = "/Dockerfile",
    ports_exposes: str = "3000",
    name: str = None,
    instant_deploy: bool = False,
    server: str = DEFAULT_SERVER
) -> str:
    """Create application using a Dockerfile

    Args:
        project_uuid: Target project UUID
        server_uuid: Target server UUID
        environment_name: Environment name
        git_repository: Git repository URL
        git_branch: Git branch
        dockerfile_location: Path to Dockerfile in repo
        ports_exposes: Ports to expose
        name: Application name
        instant_deploy: Deploy immediately
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    data = {
        "project_uuid": project_uuid,
        "server_uuid": server_uuid,
        "environment_name": environment_name,
        "git_repository": git_repository,
        "git_branch": git_branch,
        "build_pack": "dockerfile",
        "dockerfile_location": dockerfile_location,
        "ports_exposes": ports_exposes,
        "instant_deploy": instant_deploy
    }
    if name:
        data["name"] = name

    result = api_request("POST", "/applications/dockerfile", server=server, data=data)
    return json.dumps(result, indent=2)


@mcp.tool()
def create_application_dockerimage(
    project_uuid: str,
    server_uuid: str,
    environment_name: str,
    docker_registry_image_name: str,
    docker_registry_image_tag: str = "latest",
    ports_exposes: str = "3000",
    name: str = None,
    instant_deploy: bool = False,
    server: str = DEFAULT_SERVER
) -> str:
    """Create application from a Docker image

    Args:
        project_uuid: Target project UUID
        server_uuid: Target server UUID
        environment_name: Environment name
        docker_registry_image_name: Docker image name (e.g., nginx, myuser/myapp)
        docker_registry_image_tag: Image tag (default: latest)
        ports_exposes: Ports to expose
        name: Application name
        instant_deploy: Deploy immediately
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    data = {
        "project_uuid": project_uuid,
        "server_uuid": server_uuid,
        "environment_name": environment_name,
        "docker_registry_image_name": docker_registry_image_name,
        "docker_registry_image_tag": docker_registry_image_tag,
        "ports_exposes": ports_exposes,
        "instant_deploy": instant_deploy
    }
    if name:
        data["name"] = name

    result = api_request("POST", "/applications/dockerimage", server=server, data=data)
    return json.dumps(result, indent=2)


@mcp.tool()
def create_application_dockercompose(
    project_uuid: str,
    server_uuid: str,
    environment_name: str,
    git_repository: str,
    git_branch: str = "main",
    docker_compose_location: str = "/docker-compose.yaml",
    name: str = None,
    instant_deploy: bool = False,
    server: str = DEFAULT_SERVER
) -> str:
    """Create application from Docker Compose file

    Args:
        project_uuid: Target project UUID
        server_uuid: Target server UUID
        environment_name: Environment name
        git_repository: Git repository URL
        git_branch: Git branch
        docker_compose_location: Path to docker-compose file
        name: Application name
        instant_deploy: Deploy immediately
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    data = {
        "project_uuid": project_uuid,
        "server_uuid": server_uuid,
        "environment_name": environment_name,
        "git_repository": git_repository,
        "git_branch": git_branch,
        "build_pack": "dockercompose",
        "docker_compose_location": docker_compose_location,
        "instant_deploy": instant_deploy
    }
    if name:
        data["name"] = name

    result = api_request("POST", "/applications/dockercompose", server=server, data=data)
    return json.dumps(result, indent=2)


# ============================================================================
# DATABASE TOOLS
# ============================================================================

@mcp.tool()
def list_databases(server: str = DEFAULT_SERVER) -> str:
    """List all databases

    Args:
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    result = api_request("GET", "/databases", server=server)
    return json.dumps(result, indent=2)


@mcp.tool()
def get_database(uuid: str, server: str = DEFAULT_SERVER) -> str:
    """Get detailed database information

    Args:
        uuid: Database UUID
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    result = api_request("GET", f"/databases/{uuid}", server=server)
    return json.dumps(result, indent=2)


@mcp.tool()
def create_database_postgresql(
    project_uuid: str,
    server_uuid: str,
    environment_name: str,
    postgres_user: str = "postgres",
    postgres_password: str = None,
    postgres_db: str = "postgres",
    name: str = None,
    description: str = None,
    image: str = "postgres:17-alpine",
    is_public: bool = False,
    public_port: int = None,
    instant_deploy: bool = True,
    server: str = DEFAULT_SERVER
) -> str:
    """Create a PostgreSQL database

    Args:
        project_uuid: Target project UUID
        server_uuid: Target server UUID
        environment_name: Environment name
        postgres_user: Database user (default: postgres)
        postgres_password: Database password (auto-generated if not provided)
        postgres_db: Database name (default: postgres)
        name: Instance name
        description: Instance description
        image: Docker image (default: postgres:17-alpine)
        is_public: Make database publicly accessible
        public_port: Public port if is_public is True
        instant_deploy: Deploy immediately
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    import secrets

    data = {
        "project_uuid": project_uuid,
        "server_uuid": server_uuid,
        "environment_name": environment_name,
        "postgres_user": postgres_user,
        "postgres_password": postgres_password or secrets.token_urlsafe(32),
        "postgres_db": postgres_db,
        "image": image,
        "is_public": is_public,
        "instant_deploy": instant_deploy
    }
    if name:
        data["name"] = name
    if description:
        data["description"] = description
    if public_port and is_public:
        data["public_port"] = public_port

    result = api_request("POST", "/databases/postgresql", server=server, data=data)
    return json.dumps(result, indent=2)


@mcp.tool()
def create_database_mysql(
    project_uuid: str,
    server_uuid: str,
    environment_name: str,
    mysql_user: str = "mysql",
    mysql_password: str = None,
    mysql_database: str = "mysql",
    mysql_root_password: str = None,
    name: str = None,
    image: str = "mysql:8",
    instant_deploy: bool = True,
    server: str = DEFAULT_SERVER
) -> str:
    """Create a MySQL database

    Args:
        project_uuid: Target project UUID
        server_uuid: Target server UUID
        environment_name: Environment name
        mysql_user: Database user
        mysql_password: User password
        mysql_database: Database name
        mysql_root_password: Root password
        name: Instance name
        image: Docker image
        instant_deploy: Deploy immediately
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    import secrets

    data = {
        "project_uuid": project_uuid,
        "server_uuid": server_uuid,
        "environment_name": environment_name,
        "mysql_user": mysql_user,
        "mysql_password": mysql_password or secrets.token_urlsafe(32),
        "mysql_database": mysql_database,
        "mysql_root_password": mysql_root_password or secrets.token_urlsafe(32),
        "image": image,
        "instant_deploy": instant_deploy
    }
    if name:
        data["name"] = name

    result = api_request("POST", "/databases/mysql", server=server, data=data)
    return json.dumps(result, indent=2)


@mcp.tool()
def create_database_redis(
    project_uuid: str,
    server_uuid: str,
    environment_name: str,
    redis_password: str = None,
    name: str = None,
    image: str = "redis:alpine",
    instant_deploy: bool = True,
    server: str = DEFAULT_SERVER
) -> str:
    """Create a Redis database

    Args:
        project_uuid: Target project UUID
        server_uuid: Target server UUID
        environment_name: Environment name
        redis_password: Redis password
        name: Instance name
        image: Docker image
        instant_deploy: Deploy immediately
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    import secrets

    data = {
        "project_uuid": project_uuid,
        "server_uuid": server_uuid,
        "environment_name": environment_name,
        "redis_password": redis_password or secrets.token_urlsafe(32),
        "image": image,
        "instant_deploy": instant_deploy
    }
    if name:
        data["name"] = name

    result = api_request("POST", "/databases/redis", server=server, data=data)
    return json.dumps(result, indent=2)


@mcp.tool()
def create_database_mongodb(
    project_uuid: str,
    server_uuid: str,
    environment_name: str,
    mongo_initdb_root_username: str = "root",
    mongo_initdb_root_password: str = None,
    mongo_initdb_database: str = "admin",
    name: str = None,
    image: str = "mongo:7",
    instant_deploy: bool = True,
    server: str = DEFAULT_SERVER
) -> str:
    """Create a MongoDB database

    Args:
        project_uuid: Target project UUID
        server_uuid: Target server UUID
        environment_name: Environment name
        mongo_initdb_root_username: Root username
        mongo_initdb_root_password: Root password
        mongo_initdb_database: Initial database
        name: Instance name
        image: Docker image
        instant_deploy: Deploy immediately
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    import secrets

    data = {
        "project_uuid": project_uuid,
        "server_uuid": server_uuid,
        "environment_name": environment_name,
        "mongo_initdb_root_username": mongo_initdb_root_username,
        "mongo_initdb_root_password": mongo_initdb_root_password or secrets.token_urlsafe(32),
        "mongo_initdb_database": mongo_initdb_database,
        "image": image,
        "instant_deploy": instant_deploy
    }
    if name:
        data["name"] = name

    result = api_request("POST", "/databases/mongodb", server=server, data=data)
    return json.dumps(result, indent=2)


@mcp.tool()
def update_database(
    uuid: str,
    name: str = None,
    description: str = None,
    image: str = None,
    is_public: bool = None,
    public_port: int = None,
    server: str = DEFAULT_SERVER
) -> str:
    """Update database configuration

    Args:
        uuid: Database UUID
        name: New name
        description: New description
        image: New Docker image
        is_public: Make database public
        public_port: Public port number
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    data = {}
    if name is not None:
        data["name"] = name
    if description is not None:
        data["description"] = description
    if image is not None:
        data["image"] = image
    if is_public is not None:
        data["is_public"] = is_public
    if public_port is not None:
        data["public_port"] = public_port

    result = api_request("PATCH", f"/databases/{uuid}", server=server, data=data)
    return json.dumps(result, indent=2)


@mcp.tool()
def delete_database(
    uuid: str,
    delete_configurations: bool = True,
    delete_volumes: bool = False,
    server: str = DEFAULT_SERVER
) -> str:
    """Delete a database

    Args:
        uuid: Database UUID
        delete_configurations: Delete configuration files
        delete_volumes: Delete data volumes (WARNING: data loss)
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    params = {
        "delete_configurations": delete_configurations,
        "delete_volumes": delete_volumes
    }
    result = api_request("DELETE", f"/databases/{uuid}", server=server, params=params)
    return json.dumps(result, indent=2)


@mcp.tool()
def start_database(uuid: str, server: str = DEFAULT_SERVER) -> str:
    """Start a database

    Args:
        uuid: Database UUID
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    result = api_request("POST", f"/databases/{uuid}/start", server=server)
    return json.dumps(result, indent=2)


@mcp.tool()
def stop_database(uuid: str, server: str = DEFAULT_SERVER) -> str:
    """Stop a database

    Args:
        uuid: Database UUID
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    result = api_request("POST", f"/databases/{uuid}/stop", server=server)
    return json.dumps(result, indent=2)


@mcp.tool()
def restart_database(uuid: str, server: str = DEFAULT_SERVER) -> str:
    """Restart a database

    Args:
        uuid: Database UUID
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    result = api_request("POST", f"/databases/{uuid}/restart", server=server)
    return json.dumps(result, indent=2)


# ============================================================================
# SERVICE TOOLS
# ============================================================================

@mcp.tool()
def list_services(server: str = DEFAULT_SERVER) -> str:
    """List all services (one-click deployable services)

    Args:
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    result = api_request("GET", "/services", server=server)
    return json.dumps(result, indent=2)


@mcp.tool()
def get_service(uuid: str, server: str = DEFAULT_SERVER) -> str:
    """Get detailed service information

    Args:
        uuid: Service UUID
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    result = api_request("GET", f"/services/{uuid}", server=server)
    return json.dumps(result, indent=2)


@mcp.tool()
def start_service(uuid: str, server: str = DEFAULT_SERVER) -> str:
    """Start a service

    Args:
        uuid: Service UUID
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    result = api_request("POST", f"/services/{uuid}/start", server=server)
    return json.dumps(result, indent=2)


@mcp.tool()
def stop_service(uuid: str, server: str = DEFAULT_SERVER) -> str:
    """Stop a service

    Args:
        uuid: Service UUID
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    result = api_request("POST", f"/services/{uuid}/stop", server=server)
    return json.dumps(result, indent=2)


@mcp.tool()
def restart_service(uuid: str, server: str = DEFAULT_SERVER) -> str:
    """Restart a service

    Args:
        uuid: Service UUID
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    result = api_request("POST", f"/services/{uuid}/restart", server=server)
    return json.dumps(result, indent=2)


@mcp.tool()
def delete_service(
    uuid: str,
    delete_configurations: bool = True,
    delete_volumes: bool = False,
    server: str = DEFAULT_SERVER
) -> str:
    """Delete a service

    Args:
        uuid: Service UUID
        delete_configurations: Delete configuration files
        delete_volumes: Delete data volumes
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    params = {
        "delete_configurations": delete_configurations,
        "delete_volumes": delete_volumes
    }
    result = api_request("DELETE", f"/services/{uuid}", server=server, params=params)
    return json.dumps(result, indent=2)


@mcp.tool()
def list_service_envs(uuid: str, server: str = DEFAULT_SERVER) -> str:
    """List environment variables for a service

    Args:
        uuid: Service UUID
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    result = api_request("GET", f"/services/{uuid}/envs", server=server)
    return json.dumps(result, indent=2)


@mcp.tool()
def create_service_env(
    uuid: str,
    key: str,
    value: str,
    is_preview: bool = False,
    server: str = DEFAULT_SERVER
) -> str:
    """Create an environment variable for a service

    Args:
        uuid: Service UUID
        key: Variable name
        value: Variable value
        is_preview: Available in preview deployments
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    data = {
        "key": key,
        "value": value,
        "is_preview": is_preview
    }
    result = api_request("POST", f"/services/{uuid}/envs", server=server, data=data)
    return json.dumps(result, indent=2)


# ============================================================================
# DEPLOYMENT TOOLS
# ============================================================================

@mcp.tool()
def list_deployments(server: str = DEFAULT_SERVER) -> str:
    """List all currently running deployments

    Args:
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    result = api_request("GET", "/deployments", server=server)
    return json.dumps(result, indent=2)


@mcp.tool()
def get_deployment(uuid: str, server: str = DEFAULT_SERVER) -> str:
    """Get deployment details

    Args:
        uuid: Deployment UUID
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    result = api_request("GET", f"/deployments/{uuid}", server=server)
    return json.dumps(result, indent=2)


@mcp.tool()
def deploy_by_uuid(uuid: str, force_rebuild: bool = False, server: str = DEFAULT_SERVER) -> str:
    """Trigger a deployment by application UUID

    Args:
        uuid: Application UUID to deploy
        force_rebuild: Force full rebuild (ignore cache)
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    params = {"uuid": uuid}
    if force_rebuild:
        params["force"] = True
    result = api_request("GET", "/deploy", server=server, params=params)
    return json.dumps(result, indent=2)


@mcp.tool()
def deploy_by_tag(tag: str, force_rebuild: bool = False, server: str = DEFAULT_SERVER) -> str:
    """Trigger deployment by tag (deploys all applications with the tag)

    Args:
        tag: Tag name to deploy
        force_rebuild: Force full rebuild
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    params = {"tag": tag}
    if force_rebuild:
        params["force"] = True
    result = api_request("GET", "/deploy", server=server, params=params)
    return json.dumps(result, indent=2)


@mcp.tool()
def list_application_deployments(uuid: str, limit: int = 10, server: str = DEFAULT_SERVER) -> str:
    """List deployment history for an application

    Args:
        uuid: Application UUID
        limit: Maximum number of deployments to return
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    result = api_request("GET", f"/applications/{uuid}/deployments", server=server, params={"limit": limit})
    return json.dumps(result, indent=2)


# ============================================================================
# TEAM TOOLS
# ============================================================================

@mcp.tool()
def list_teams(server: str = DEFAULT_SERVER) -> str:
    """List all teams

    Args:
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    result = api_request("GET", "/teams", server=server)
    return json.dumps(result, indent=2)


@mcp.tool()
def get_team(team_id: int, server: str = DEFAULT_SERVER) -> str:
    """Get team details

    Args:
        team_id: Team ID
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    result = api_request("GET", f"/teams/{team_id}", server=server)
    return json.dumps(result, indent=2)


@mcp.tool()
def get_team_members(team_id: int, server: str = DEFAULT_SERVER) -> str:
    """Get team members

    Args:
        team_id: Team ID
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    result = api_request("GET", f"/teams/{team_id}/members", server=server)
    return json.dumps(result, indent=2)


# ============================================================================
# PRIVATE KEYS TOOLS
# ============================================================================

@mcp.tool()
def list_private_keys(server: str = DEFAULT_SERVER) -> str:
    """List all private keys (SSH deploy keys)

    Args:
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    result = api_request("GET", "/security/keys", server=server)
    return json.dumps(result, indent=2)


@mcp.tool()
def get_private_key(uuid: str, server: str = DEFAULT_SERVER) -> str:
    """Get private key details

    Args:
        uuid: Private key UUID
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    result = api_request("GET", f"/security/keys/{uuid}", server=server)
    return json.dumps(result, indent=2)


@mcp.tool()
def create_private_key(
    name: str,
    private_key: str,
    description: str = "",
    server: str = DEFAULT_SERVER
) -> str:
    """Create a new private key for deployments

    Args:
        name: Key name
        private_key: SSH private key content
        description: Key description
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    data = {
        "name": name,
        "private_key": private_key
    }
    if description:
        data["description"] = description

    result = api_request("POST", "/security/keys", server=server, data=data)
    return json.dumps(result, indent=2)


@mcp.tool()
def delete_private_key(uuid: str, server: str = DEFAULT_SERVER) -> str:
    """Delete a private key

    Args:
        uuid: Private key UUID
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    result = api_request("DELETE", f"/security/keys/{uuid}", server=server)
    return json.dumps(result, indent=2)


# ============================================================================
# UTILITY TOOLS
# ============================================================================

@mcp.tool()
def get_resources_summary(server: str = DEFAULT_SERVER) -> str:
    """Get a summary of all resources (applications, databases, services) with their status

    Args:
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    summary = {
        "server": server,
        "server_info": SERVERS[server]["description"],
        "generated_at": datetime.now().isoformat(),
        "applications": [],
        "databases": [],
        "services": []
    }

    # Get applications
    apps = api_request("GET", "/applications", server=server)
    if isinstance(apps, list):
        for app in apps:
            summary["applications"].append({
                "uuid": app.get("uuid"),
                "name": app.get("name"),
                "status": app.get("status"),
                "fqdn": app.get("fqdn"),
                "last_online": app.get("last_online_at")
            })

    # Get databases
    dbs = api_request("GET", "/databases", server=server)
    if isinstance(dbs, list):
        for db in dbs:
            summary["databases"].append({
                "uuid": db.get("uuid"),
                "name": db.get("name"),
                "type": db.get("type"),
                "status": db.get("status")
            })

    # Get services
    services = api_request("GET", "/services", server=server)
    if isinstance(services, list):
        for svc in services:
            summary["services"].append({
                "uuid": svc.get("uuid"),
                "name": svc.get("name"),
                "status": svc.get("status")
            })

    return json.dumps(summary, indent=2)


@mcp.tool()
def quick_status(server: str = DEFAULT_SERVER) -> str:
    """Get a quick status overview of all resources

    Args:
        server: Which Coolify server to use ('hetzner' or 'faric'). Default: hetzner
    """
    apps = api_request("GET", "/applications", server=server)
    dbs = api_request("GET", "/databases", server=server)
    services = api_request("GET", "/services", server=server)

    status = {
        "server": server,
        "server_info": SERVERS[server]["description"],
        "timestamp": datetime.now().isoformat(),
        "summary": {
            "applications": {
                "total": len(apps) if isinstance(apps, list) else 0,
                "healthy": sum(1 for a in apps if isinstance(apps, list) and "healthy" in str(a.get("status", ""))),
                "unhealthy": sum(1 for a in apps if isinstance(apps, list) and "unhealthy" in str(a.get("status", "")))
            },
            "databases": {
                "total": len(dbs) if isinstance(dbs, list) else 0,
                "healthy": sum(1 for d in dbs if isinstance(dbs, list) and "healthy" in str(d.get("status", "")))
            },
            "services": {
                "total": len(services) if isinstance(services, list) else 0
            }
        },
        "resources": []
    }

    if isinstance(apps, list):
        for app in apps:
            status["resources"].append({
                "type": "application",
                "name": app.get("name"),
                "uuid": app.get("uuid"),
                "status": app.get("status")
            })

    if isinstance(dbs, list):
        for db in dbs:
            status["resources"].append({
                "type": "database",
                "name": db.get("name"),
                "uuid": db.get("uuid"),
                "status": db.get("status")
            })

    return json.dumps(status, indent=2)


@mcp.tool()
def get_all_servers_status() -> str:
    """Get status overview of ALL Coolify server instances (both hetzner and faric)

    Returns combined status from both servers for a complete infrastructure view.
    """
    combined = {
        "timestamp": datetime.now().isoformat(),
        "servers": {}
    }

    for server_id in SERVERS.keys():
        try:
            apps = api_request("GET", "/applications", server=server_id)
            dbs = api_request("GET", "/databases", server=server_id)
            services = api_request("GET", "/services", server=server_id)

            combined["servers"][server_id] = {
                "info": SERVERS[server_id]["description"],
                "url": SERVERS[server_id]["url"],
                "status": "healthy",
                "applications": len(apps) if isinstance(apps, list) else 0,
                "databases": len(dbs) if isinstance(dbs, list) else 0,
                "services": len(services) if isinstance(services, list) else 0
            }
        except Exception as e:
            combined["servers"][server_id] = {
                "info": SERVERS[server_id]["description"],
                "url": SERVERS[server_id]["url"],
                "status": "error",
                "error": str(e)
            }

    return json.dumps(combined, indent=2)


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    mcp.run()
