import logging
import time
import re
import os
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.config import settings
from app.integrations.bedrock.client import BedrockClient
from app.utils.ddstarter.mcp_client import DatadogMCPClient

logger = logging.getLogger(__name__)

router = APIRouter()

class BedrockHealthRequest(BaseModel):
    prompt: Optional[str] = "Hello, Bedrock! Are you online?"
    model_id: Optional[str] = None

class LogEntry(BaseModel):
    timestamp: str
    level: str
    service: str
    message: str

def mask_key(key: Optional[str]) -> str:
    if not key:
        return "Not Set"
    if len(key) <= 8:
        return "***"
    return f"{key[:4]}...{key[-4:]}"

def parse_tsv_logs(tsv_text: str) -> List[Dict[str, str]]:
    """Parse TSV format output from search_datadog_logs tool."""
    match = re.search(r'<TSV_DATA>(.*?)</TSV_DATA>', tsv_text, re.DOTALL)
    if not match:
        return []
    tsv_content = match.group(1).strip()
    if not tsv_content:
        return []
    
    lines = tsv_content.split('\n')
    if len(lines) < 2:
        return []
    
    headers = [h.strip().lower() for h in lines[0].split('\t')]
    logs = []
    
    # Map headers like 'date', 'status', 'message', 'service' to standard normalized fields
    for line in lines[1:]:
        if not line.strip():
            continue
        parts = line.split('\t')
        if len(parts) < len(headers):
            parts += [''] * (len(headers) - len(parts))
        row = dict(zip(headers, parts))
        
        # Normalize fields
        timestamp = row.get('timestamp') or row.get('date') or row.get('time') or ""
        # Format ISO timestamp to hh:mm:ss if possible
        if timestamp and "T" in timestamp:
            try:
                # E.g. 2026-06-25T11:00:00Z -> 11:00:00
                time_part = timestamp.split("T")[1][:8]
                timestamp = time_part
            except Exception:
                pass
        elif not timestamp:
            timestamp = time.strftime("%H:%M:%S")

        level = row.get('level') or row.get('status') or row.get('severity') or "INFO"
        level = level.upper()
        if level not in ("INFO", "WARN", "ERROR"):
            level = "INFO"
            
        service = row.get('service') or row.get('source') or "unknown-service"
        message = row.get('message') or row.get('content') or ""
        
        if message:
            logs.append({
                "timestamp": timestamp,
                "level": level,
                "service": service,
                "message": message
            })
            
    return logs

@router.post("/bedrock-health")
def test_bedrock_health(req: BedrockHealthRequest):
    """
    Invokes AWS Bedrock with a custom test prompt and measures latency.
    """
    start_time = time.time()
    try:
        client = BedrockClient()
        response_text = client.run_chat_turn(
            history=[],
            message=req.prompt,
            model_id=req.model_id
        )
        latency_ms = int((time.time() - start_time) * 1000)
        
        return {
            "status": "healthy",
            "latency_ms": latency_ms,
            "model_used": req.model_id or settings.BEDROCK_MODEL_ID,
            "response": response_text
        }
    except Exception as e:
        logger.error(f"Bedrock health test failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AWS Bedrock is unhealthy: {str(e)}"
        )

@router.get("/bedrock-diagnostics")
def test_bedrock_diagnostics():
    """
    Evaluates key configurations (AWS and Datadog API keys) and masked environment values.
    """
    return {
        "aws_region": settings.AWS_REGION,
        "bedrock_model_id": settings.BEDROCK_MODEL_ID,
        "aws_access_key_id_configured": bool(settings.AWS_ACCESS_KEY_ID),
        "aws_access_key_id_masked": mask_key(settings.AWS_ACCESS_KEY_ID),
        "aws_secret_access_key_configured": bool(settings.AWS_SECRET_ACCESS_KEY),
        "aws_secret_access_key_masked": mask_key(settings.AWS_SECRET_ACCESS_KEY),
        "dd_api_key_configured": bool(settings.DD_API_KEY),
        "dd_api_key_masked": mask_key(settings.DD_API_KEY),
        "dd_app_key_configured": bool(settings.DD_APP_KEY),
        "dd_app_key_masked": mask_key(settings.DD_APP_KEY),
        "dd_llmobs_ml_app": settings.DD_LLMOBS_ML_APP,
        "dd_site": settings.DD_SITE
    }

@router.get("/logs", response_model=List[LogEntry])
def get_logs(query: str = "*", limit: int = 50):
    """
    Fetch real logs from the Datadog MCP server.
    Falls back to simulated logs if Datadog returns 0 matches or credentials are empty.
    """
    fallback_logs = [
        {"timestamp": time.strftime("%H:%M:%S", time.localtime(time.time() - 900)), "level": "INFO", "service": "gateway-api", "message": "Router initializing route definitions..."},
        {"timestamp": time.strftime("%H:%M:%S", time.localtime(time.time() - 840)), "level": "INFO", "service": "user-api", "message": "DB Connection pool initialized [max_connections=20]"},
        {"timestamp": time.strftime("%H:%M:%S", time.localtime(time.time() - 780)), "level": "INFO", "service": "checkout-api", "message": "Listening on port 8080"},
        {"timestamp": time.strftime("%H:%M:%S", time.localtime(time.time() - 720)), "level": "INFO", "service": "payment-api", "message": "Payment gateway connection verified."},
        {"timestamp": time.strftime("%H:%M:%S", time.localtime(time.time() - 660)), "level": "INFO", "service": "gateway-api", "message": "GET /services - 200 OK - 12ms"},
        {"timestamp": time.strftime("%H:%M:%S", time.localtime(time.time() - 600)), "level": "INFO", "service": "inventory-api", "message": "Syncing stock database cache..."},
        {"timestamp": time.strftime("%H:%M:%S", time.localtime(time.time() - 540)), "level": "WARN", "service": "payment-api", "message": "Stripe API connection timeout. Retrying request [attempt=1/3]..."},
        {"timestamp": time.strftime("%H:%M:%S", time.localtime(time.time() - 480)), "level": "INFO", "service": "checkout-api", "message": "POST /checkout - 201 Created - 482ms"},
        {"timestamp": time.strftime("%H:%M:%S", time.localtime(time.time() - 420)), "level": "ERROR", "service": "payment-api", "message": "SocketTimeoutException: Connection reset by peer at stripe.com"},
        {"timestamp": time.strftime("%H:%M:%S", time.localtime(time.time() - 360)), "level": "WARN", "service": "checkout-api", "message": "Orchestrator latency spike detected: payment-api took 5120ms"},
    ]
    
    # Try calling Datadog MCP
    if settings.DD_API_KEY and settings.DD_APP_KEY:
        try:
            mcp_client = DatadogMCPClient()
            mcp_client.initialize()
            
            # Fetch recent logs using the Datadog MCP server
            tsv_output = mcp_client.call_tool("search_datadog_logs", {
                "query": query,
                "telemetry": {"intent": "Retrieve live log stream for SRE Operations Terminal"},
                "from": "now-30m"
            })
            
            parsed_logs = parse_tsv_logs(tsv_output)
            if parsed_logs:
                # Return limited set of real logs
                return parsed_logs[:limit]
            else:
                # Add notice that we queried MCP successfully but it was empty
                notice_log = {
                    "timestamp": time.strftime("%H:%M:%S"),
                    "level": "INFO",
                    "service": "datadog-mcp",
                    "message": "Connected to Datadog MCP server successfully, but query returned 0 matches. Displaying simulated telemetry."
                }
                return [notice_log] + fallback_logs[:limit - 1]
                
        except Exception as e:
            logger.warning(f"Failed to fetch logs from Datadog MCP, falling back to simulated logs: {e}")
            error_notice = {
                "timestamp": time.strftime("%H:%M:%S"),
                "level": "WARN",
                "service": "datadog-mcp",
                "message": f"Datadog MCP query failed ({str(e)}). Displaying simulated telemetry."
            }
            return [error_notice] + fallback_logs[:limit - 1]
    else:
        info_notice = {
            "timestamp": time.strftime("%H:%M:%S"),
            "level": "WARN",
            "service": "datadog-mcp",
            "message": "DD_API_KEY or DD_APP_KEY missing in backend/.env. Displaying simulated telemetry."
        }
        return [info_notice] + fallback_logs[:limit - 1]
