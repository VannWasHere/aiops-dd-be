import json
import logging
from typing import List, Optional, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import boto3

from app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

# --- MCP Client (inline to avoid ddtrace import chain) ---

import requests as http_requests

def _mcp_call(tool_name: str, arguments: dict) -> str:
    api_key = settings.datadog_api_key_val
    app_key = settings.datadog_app_key_val
    mcp_url = settings.mcp_server_url_val or "https://mcp.datadoghq.com/v1/mcp?toolsets=all"

    if not api_key or not app_key:
        raise ValueError("DD_API_KEY and DD_APP_KEY must be configured")

    headers = {
        "Content-Type": "application/json",
        "DD-API-KEY": api_key,
        "DD-APPLICATION-KEY": app_key,
        "Accept": "application/json, text/event-stream"
    }

    # Initialize
    resp = http_requests.post(mcp_url, json={
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "aiops-dashboard", "version": "1.0"}}
    }, headers=headers, timeout=15)
    session_id = resp.headers.get("Mcp-Session-Id", "")
    headers["Mcp-Session-Id"] = session_id

    # Call tool
    resp2 = http_requests.post(mcp_url, json={
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments}
    }, headers=headers, timeout=30)
    data = resp2.json()
    content = data.get("result", {}).get("content", [])
    return content[0].get("text", "") if content else ""


def _ask_bedrock(prompt: str) -> str:
    """Call Amazon Bedrock directly without ddtrace dependency."""
    model_id = settings.BEDROCK_MODEL_ID or "amazon.nova-pro-v1:0"
    region = settings.AWS_REGION or "us-east-1"

    client = boto3.client(
        "bedrock-runtime",
        region_name=region,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None,
    )
    response = client.invoke_model(
        modelId=model_id,
        body=json.dumps({
            "messages": [{"role": "user", "content": [{"text": prompt}]}],
            "inferenceConfig": {"max_new_tokens": 1500}
        }),
        contentType="application/json"
    )
    result_body = json.loads(response["body"].read())
    return result_body["output"]["message"]["content"][0]["text"]


# --- Models ---

class DashboardWidget(BaseModel):
    id: str = ""
    title: str = ""
    widget_type: str = ""
    group: str = ""
    queries: List[str] = []


class DashboardSummaryResponse(BaseModel):
    dashboard_id: str
    title: str
    description: str
    url: str
    groups: List[str] = []
    widgets: List[DashboardWidget] = []
    ai_summary: str = ""
    raw_data: Any = None


# --- Endpoints ---

@router.get("/llm-dashboard", response_model=DashboardSummaryResponse)
def get_llm_dashboard_with_summary():
    """Fetch 'LLM Sample Dashboard' (vy7-7se-ryv) from Datadog MCP and summarize with Bedrock."""
    try:
        raw = _mcp_call("get_datadog_dashboard", {"dashboard_id": "vy7-7se-ryv"})
        dashboard = json.loads(raw) if raw else {}
    except Exception as e:
        logger.error(f"Failed to fetch dashboard from MCP: {e}")
        raise HTTPException(status_code=502, detail=f"MCP error: {str(e)}")

    # Extract widget info
    widgets = []
    groups = []
    for w in dashboard.get("widgets", []):
        defn = w.get("definition", {})
        wtype = defn.get("type", "")
        title = defn.get("title", "")

        if wtype == "group":
            groups.append(title)
            for sub in defn.get("widgets", []):
                sub_def = sub.get("definition", {})
                queries = []
                for req in sub_def.get("requests", []):
                    for q in req.get("queries", []):
                        queries.append(q.get("query", ""))
                widgets.append(DashboardWidget(
                    id=str(sub.get("id", "")),
                    title=sub_def.get("title", ""),
                    widget_type=sub_def.get("type", ""),
                    group=title,
                    queries=queries
                ))
        else:
            queries = []
            for req in defn.get("requests", []):
                for q in req.get("queries", []):
                    queries.append(q.get("query", ""))
            widgets.append(DashboardWidget(
                id=str(w.get("id", "")),
                title=title,
                widget_type=wtype,
                group="",
                queries=queries
            ))

    # Build prompt for Bedrock summarization
    widget_summary_text = "\n".join(
        f"- [{w.group}] {w.title} ({w.widget_type}): queries={w.queries}" for w in widgets[:30]
    )
    template_vars = dashboard.get("template_variables", [])
    tv_text = ", ".join(f"{tv.get('name')}={tv.get('defaults', [])}" for tv in template_vars)

    prompt = f"""You are an AI ops analyst. Summarize this Datadog LLM Observability dashboard for an engineering team.

Dashboard: {dashboard.get('title', 'LLM Sample Dashboard')}
Description: {dashboard.get('description', '')}
Template Variables: {tv_text}
Groups: {', '.join(groups)}

Widgets:
{widget_summary_text}

Provide a concise executive summary (3-5 paragraphs) covering:
1. What this dashboard monitors and its purpose
2. Key metrics tracked (tokens, cost, performance, errors)
3. The models and apps being monitored
4. Actionable insights an SRE team should watch for
5. How MCP usage ties into the observability story

Be specific about the metric names and what they indicate. Keep it professional and actionable."""

    # Call Bedrock for AI summary
    ai_summary = ""
    try:
        ai_summary = _ask_bedrock(prompt)
    except Exception as e:
        logger.warning(f"Bedrock summarization failed: {e}")
        ai_summary = f"[Bedrock unavailable: {str(e)}]"

    return DashboardSummaryResponse(
        dashboard_id=dashboard.get("dashboard_id", "vy7-7se-ryv"),
        title=dashboard.get("title", "LLM Sample Dashboard"),
        description=dashboard.get("description", ""),
        url=dashboard.get("url", "https://app.datadoghq.com/dashboard/vy7-7se-ryv"),
        groups=groups,
        widgets=widgets,
        ai_summary=ai_summary,
        raw_data=dashboard
    )
