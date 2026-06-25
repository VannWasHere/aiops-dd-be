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


class NodeInfo(BaseModel):
    id: str
    label: str
    type: str  # service, database, cache, external
    status: str  # operational, degraded, offline

class EdgeInfo(BaseModel):
    source: str
    target: str

class DependencyGraphResponse(BaseModel):
    nodes: List[NodeInfo]
    edges: List[EdgeInfo]
    status_info: str

class SpanEntry(BaseModel):
    id: str
    service: str
    operation: str
    status: str
    latency_ms: int
    http_status: str

class SpansResponse(BaseModel):
    spans: List[SpanEntry]
    status_info: str

class MetricsResponse(BaseModel):
    cpu: List[float]
    memory: List[float]
    status_info: str


@router.get("/dependencies", response_model=DependencyGraphResponse)
def get_dependencies():
    fallback_nodes = [
        {"id": "gateway-api", "label": "gateway-api", "type": "service", "status": "operational"},
        {"id": "checkout-api", "label": "checkout-api", "type": "service", "status": "operational"},
        {"id": "payment-api", "label": "payment-api", "type": "service", "status": "degraded"},
        {"id": "inventory-api", "label": "inventory-api", "type": "service", "status": "operational"},
        {"id": "redis-cache", "label": "redis-cache", "type": "cache", "status": "operational"},
        {"id": "postgres-db", "label": "postgres-db", "type": "database", "status": "operational"},
        {"id": "stripe-gateway", "label": "stripe-gateway", "type": "external", "status": "degraded"}
    ]
    fallback_edges = [
        {"source": "gateway-api", "target": "checkout-api"},
        {"source": "gateway-api", "target": "payment-api"},
        {"source": "checkout-api", "target": "inventory-api"},
        {"source": "payment-api", "target": "stripe-gateway"},
        {"source": "payment-api", "target": "redis-cache"},
        {"source": "redis-cache", "target": "postgres-db"},
        {"source": "inventory-api", "target": "postgres-db"}
    ]
    
    if settings.DD_API_KEY and settings.DD_APP_KEY:
        try:
            mcp_client = DatadogMCPClient()
            mcp_client.initialize()
            
            # Query MCP dependencies
            resp = mcp_client.call_tool("search_datadog_service_dependencies", {
                "service": "gateway-api",
                "direction": "downstream",
                "telemetry": {"intent": "Retrieve downstream service dependencies for visual graph"}
            })
            
            # Parse dependency output if available (e.g. from TSV block)
            match = re.search(r'<TSV_DATA>(.*?)</TSV_DATA>', resp, re.DOTALL)
            if match and match.group(1).strip():
                lines = match.group(1).strip().split('\n')
                if len(lines) > 1:
                    nodes = set()
                    edges = []
                    headers = [h.strip().lower() for h in lines[0].split('\t')]
                    for line in lines[1:]:
                        if not line.strip():
                            continue
                        parts = line.split('\t')
                        row = dict(zip(headers, parts))
                        src = row.get('service') or row.get('source_service')
                        tgt = row.get('dependency') or row.get('destination_service')
                        if src and tgt:
                            nodes.add(src)
                            nodes.add(tgt)
                            edges.append({"source": src, "target": tgt})
                    
                    if nodes and edges:
                        node_list = []
                        for node in nodes:
                            # Classify node type
                            node_type = "service"
                            if "db" in node or "postgres" in node:
                                node_type = "database"
                            elif "cache" in node or "redis" in node:
                                node_type = "cache"
                            elif "gateway" in node or "stripe" in node:
                                node_type = "external"
                            node_list.append({
                                "id": node,
                                "label": node,
                                "type": node_type,
                                "status": "operational"
                            })
                        return DependencyGraphResponse(
                            nodes=node_list,
                            edges=edges,
                            status_info="live"
                        )
            
            return DependencyGraphResponse(
                nodes=fallback_nodes,
                edges=fallback_edges,
                status_info="simulated (Datadog returned empty dependency graph)"
            )
        except Exception as e:
            logger.warning(f"Failed to query service dependencies from MCP: {e}")
            return DependencyGraphResponse(
                nodes=fallback_nodes,
                edges=fallback_edges,
                status_info=f"simulated (MCP query failed: {str(e)})"
            )
    else:
        return DependencyGraphResponse(
            nodes=fallback_nodes,
            edges=fallback_edges,
            status_info="simulated (Datadog credentials missing)"
        )


@router.get("/spans", response_model=SpansResponse)
def get_spans():
    # Build slightly randomized fallback transaction spans to represent state
    lat_checkout = random.randint(18, 28)
    lat_stripe = random.randint(4800, 5200)
    lat_gateway = lat_stripe + random.randint(10, 25)
    
    fallback_spans = [
        SpanEntry(
            id="span-101",
            service="checkout-api",
            operation="inventory-api.check_stock",
            status="operational",
            latency_ms=lat_checkout,
            http_status="200 OK"
        ),
        SpanEntry(
            id="span-102",
            service="payment-api",
            operation="stripe.charge",
            status="offline",
            latency_ms=lat_stripe,
            http_status="504 TIMEOUT"
        ),
        SpanEntry(
            id="span-103",
            service="gateway-api",
            operation="payment-api.process_payment",
            status="degraded",
            latency_ms=lat_gateway,
            http_status="504 GATEWAY"
        )
    ]
    
    if settings.DD_API_KEY and settings.DD_APP_KEY:
        try:
            mcp_client = DatadogMCPClient()
            mcp_client.initialize()
            
            # Query spans from MCP
            resp = mcp_client.call_tool("search_datadog_spans", {
                "query": "service:* status:error",
                "from": "now-15m",
                "telemetry": {"intent": "Retrieve transaction error spans for active UI widget"}
            })
            
            # Parse spans if any (JSON, YAML, or text)
            if "trace_id" in resp or "span_id" in resp or "service" in resp:
                try:
                    json_match = re.search(r'<JSON_DATA>(.*?)</JSON_DATA>', resp, re.DOTALL)
                    spans_list = []
                    if json_match and json_match.group(1).strip():
                        spans_data = json.loads(json_match.group(1).strip())
                        if isinstance(spans_data, list):
                            for idx, s in enumerate(spans_data[:5]):
                                spans_list.append(SpanEntry(
                                    id=s.get("span_id") or f"span-{idx}",
                                    service=s.get("service", "unknown"),
                                    operation=s.get("name", "operation"),
                                    status="offline" if s.get("status") == "error" else "operational",
                                    latency_ms=int(s.get("duration", 0) / 1000000), # ns to ms
                                    http_status="500 ERROR" if s.get("status") == "error" else "200 OK"
                                ))
                    
                    if spans_list:
                        return SpansResponse(spans=spans_list, status_info="live")
                except Exception as parse_err:
                    logger.warning(f"Error parsing trace spans: {parse_err}")
            
            return SpansResponse(spans=fallback_spans, status_info="simulated (Datadog returned empty traces)")
        except Exception as e:
            logger.warning(f"Failed to query trace spans from MCP: {e}")
            return SpansResponse(spans=fallback_spans, status_info=f"simulated (MCP query failed: {str(e)})")
    else:
        return SpansResponse(spans=fallback_spans, status_info="simulated (Datadog credentials missing)")


@router.get("/metrics", response_model=MetricsResponse)
def get_metrics():
    # Simulated metrics arrays
    fallback_cpu = [random.randint(45, 95) for _ in range(12)]
    fallback_mem = [random.randint(68, 78) for _ in range(12)]
    
    if settings.DD_API_KEY and settings.DD_APP_KEY:
        try:
            mcp_client = DatadogMCPClient()
            mcp_client.initialize()
            
            # Query CPU metrics
            cpu_resp = mcp_client.call_tool("get_datadog_metric", {
                "queries": ["avg:system.cpu.user{*}"],
                "from": "now-1h",
                "telemetry": {"intent": "Query CPU usage timeseries data for visual chart"}
            })
            
            # Query Memory metrics
            mem_resp = mcp_client.call_tool("get_datadog_metric", {
                "queries": ["avg:system.mem.pct_usable{*}"],
                "from": "now-1h",
                "telemetry": {"intent": "Query Memory usable timeseries data for visual chart"}
            })
            
            def parse_metric_timeseries(resp_text: str) -> List[float]:
                json_match = re.search(r'<JSON_DATA>(.*?)</JSON_DATA>', resp_text, re.DOTALL)
                if not json_match:
                    return []
                content = json_match.group(1).strip()
                if not content:
                    return []
                try:
                    data = json.loads(content)
                    points = []
                    series_list = []
                    if isinstance(data, list):
                        series_list = data
                    elif isinstance(data, dict):
                        series_list = data.get("series") or data.get("timeseries") or []
                        
                    for s in series_list:
                        if "points" in s:
                            series_points = [p[1] for p in s["points"] if p[1] is not None]
                            if series_points:
                                points = series_points
                                break
                    return points
                except Exception:
                    return []
                    
            cpu_points = parse_metric_timeseries(cpu_resp)
            mem_points = parse_metric_timeseries(mem_resp)
            
            # Convert Memory pct_usable to Memory footprint pct (100 - usable)
            if mem_points:
                mem_points = [max(0, min(100, 100 - p)) for p in mem_points]
                
            def downsample(pts: List[float], fallback_list: List[float]) -> List[float]:
                if not pts:
                    return fallback_list
                if len(pts) == 12:
                    return pts
                if len(pts) < 12:
                    avg_val = sum(pts) / len(pts)
                    padded = list(pts)
                    while len(padded) < 12:
                        padded.append(avg_val + random.uniform(-5, 5))
                    return padded
                step = len(pts) / 12.0
                res = []
                for i in range(12):
                    idx = int(i * step)
                    res.append(pts[min(idx, len(pts)-1)])
                return res

            final_cpu = downsample(cpu_points, fallback_cpu)
            final_mem = downsample(mem_points, fallback_mem)
            
            final_cpu = [round(v, 1) for v in final_cpu]
            final_mem = [round(v, 1) for v in final_mem]
            
            has_live = bool(cpu_points or mem_points)
            return MetricsResponse(
                cpu=final_cpu,
                memory=final_mem,
                status_info="live" if has_live else "simulated (Datadog returned empty metrics)"
            )
            
        except Exception as e:
            logger.warning(f"Failed to fetch metric timeseries from MCP: {e}")
            return MetricsResponse(
                cpu=fallback_cpu,
                memory=fallback_mem,
                status_info=f"simulated (MCP query failed: {str(e)})"
            )
    else:
        return MetricsResponse(
            cpu=fallback_cpu,
            memory=fallback_mem,
            status_info="simulated (Datadog credentials missing)"
        )
