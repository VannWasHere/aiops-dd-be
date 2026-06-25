import os
import logging
import requests
from typing import Dict, Any, List
from app.core.config import settings

logger = logging.getLogger(__name__)

class DatadogMCPClient:
    """
    Client for Datadog MCP Server to fetch metrics, logs, spans, and monitors.
    """
    def __init__(self, mcp_url: str = None, api_key: str = None, app_key: str = None):
        self.mcp_url = mcp_url or "https://mcp.datadoghq.com/api/unstable/mcp-server/mcp"
        self.api_key = api_key or settings.DD_API_KEY
        self.app_key = app_key or settings.DD_APP_KEY
        self._id = 0
        self._session_id = None
        
        self.headers = {
            "Content-Type": "application/json",
            "DD-API-KEY": self.api_key or "",
            "DD-APPLICATION-KEY": self.app_key or "",
            "Accept": "application/json, text/event-stream"
        }

    def _post(self, method: str, params: dict = None) -> dict:
        if not self.api_key or not self.app_key:
            raise ValueError("Datadog API key or Application key not configured.")

        self._id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._id,
            "method": method,
            "params": params or {}
        }
        
        req_headers = {**self.headers}
        if self._session_id:
            req_headers["Mcp-Session-Id"] = self._session_id
            
        try:
            response = requests.post(self.mcp_url, json=payload, headers=req_headers, timeout=15)
            response.raise_for_status()
            
            if "Mcp-Session-Id" in response.headers:
                self._session_id = response.headers["Mcp-Session-Id"]
                
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"MCP JSON-RPC request to {method} failed: {e}")
            raise RuntimeError(f"Datadog MCP Server request failed: {str(e)}") from e

    def initialize(self):
        """Perform initial handshake with the MCP server."""
        try:
            self._post("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "aiops-backend-mcp", "version": "1.0"}
            })
            logger.info("Successfully initialized connection to Datadog MCP Server")
        except Exception as e:
            logger.error(f"Failed to initialize Datadog MCP Client: {e}")
            raise

    def list_tools(self) -> List[Dict[str, Any]]:
        """List all available tools on the Datadog MCP server."""
        result = self._post("tools/list")
        return result.get("result", {}).get("tools", [])

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> str:
        """Call a specific tool on the Datadog MCP server."""
        try:
            result = self._post("tools/call", {"name": name, "arguments": arguments})
            content = result.get("result", {}).get("content", [])
            if content:
                # Typically content is a list containing text dicts
                return content[0].get("text", "")
            return ""
        except Exception as e:
            logger.error(f"Failed to call MCP tool '{name}': {e}")
            raise
