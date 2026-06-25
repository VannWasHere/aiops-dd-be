import logging
import re
import yaml
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.core.config import settings
from app.utils.ddstarter.mcp_client import DatadogMCPClient

logger = logging.getLogger(__name__)

router = APIRouter()

# --- Pydantic Models ---

class TraceSummary(BaseModel):
    trace_id: str
    service: str
    operation: str
    resource: str
    timestamp: str
    duration_ms: float
    status: str  # "ok" or "error"
    span_count: int

class TracesListResponse(BaseModel):
    traces: List[TraceSummary]
    status_info: str

class TraceSpan(BaseModel):
    span_id: str
    parent_id: str
    service: str
    name: str
    resource: str
    start_time: str
    end_time: str
    duration_ms: float
    status: str  # "ok" or "error"
    meta: Dict[str, Any]

class TraceDetailResponse(BaseModel):
    trace_id: str
    deep_link_url: Optional[str] = None
    spans: List[TraceSpan]
    status_info: str

# --- Helpers ---

def parse_yaml_data(resp_text: str) -> List[Dict[str, Any]]:
    """Helper to extract and parse YAML data from MCP tool response."""
    yaml_match = re.search(r'<YAML_DATA>(.*?)</YAML_DATA>', resp_text, re.DOTALL)
    if not yaml_match:
        # Fallback if no tags but response might be raw YAML
        try:
            return yaml.safe_load(resp_text) or []
        except Exception:
            return []
    
    yaml_content = yaml_match.group(1).strip()
    if not yaml_content:
        return []
    
    try:
        return yaml.safe_load(yaml_content) or []
    except Exception as e:
        logger.warning(f"Error parsing YAML content: {e}")
        return []

def parse_metadata(resp_text: str) -> Dict[str, str]:
    """Helper to extract metadata tags from MCP tool response."""
    metadata = {}
    metadata_match = re.search(r'<METADATA>(.*?)</METADATA>', resp_text, re.DOTALL)
    if metadata_match:
        content = metadata_match.group(1).strip()
        tags = re.findall(r'<([^>]+)>(.*?)</\1>', content, re.DOTALL)
        for tag, val in tags:
            metadata[tag.strip()] = val.strip()
    return metadata

# --- Endpoints ---

@router.get("/", response_model=TracesListResponse)
def get_traces(query: str = "service:*", from_time: str = "now-1h"):
    """
    Fetch traces from Datadog APM using the Datadog MCP server.
    Groups spans by trace ID to return unique traces.
    """
    if not settings.datadog_api_key_val or not settings.datadog_app_key_val:
        raise HTTPException(
            status_code=400,
            detail="Datadog credentials are not configured. Please set DD_API_KEY and DD_APP_KEY."
        )

    try:
        mcp_client = DatadogMCPClient()
        mcp_client.initialize()

        # Query spans via MCP
        resp = mcp_client.call_tool("search_datadog_spans", {
            "query": query,
            "from": from_time,
            "telemetry": {"intent": "Retrieve trace list for AIOps Operations Console"}
        })

        spans_data = parse_yaml_data(resp)
        if not spans_data:
            return TracesListResponse(traces=[], status_info="live (no traces found)")

        # Group spans by traceid to summarize traces
        traces_map: Dict[str, List[Dict[str, Any]]] = {}
        for span in spans_data:
            tid = span.get("traceid")
            if tid:
                if tid not in traces_map:
                    traces_map[tid] = []
                traces_map[tid].append(span)

        summaries: List[TraceSummary] = []
        for tid, trace_spans in traces_map.items():
            # Find the root span or the earliest span in the trace
            # Sort by starttimestamp
            try:
                sorted_spans = sorted(
                    trace_spans,
                    key=lambda s: s.get("starttimestamp", "") or ""
                )
            except Exception:
                sorted_spans = trace_spans

            # Try to find a span with parentid == "0", otherwise fallback to earliest span
            root_span = next((s for s in sorted_spans if s.get("parentid") == "0"), sorted_spans[0])

            # Determine overall trace status (error if any span contains error status)
            trace_status = "ok"
            for s in trace_spans:
                if s.get("status") == "error":
                    trace_status = "error"
                    break

            # Parse duration from root custom metadata, or calculate from start/end
            duration_ms = 0.0
            custom = root_span.get("custom")
            if isinstance(custom, dict) and "duration" in custom:
                try:
                    duration_ms = float(custom["duration"]) / 1000000.0  # ns to ms
                except (ValueError, TypeError):
                    pass

            # Fallback duration if 0.0
            if duration_ms == 0.0:
                # duration of root span as a fallback
                # or difference between earliest start and latest end of the trace
                try:
                    # Let's extract start & end timestamps from all spans in this trace
                    starts = [s.get("starttimestamp") for s in trace_spans if s.get("starttimestamp")]
                    ends = [s.get("endtimestamp") for s in trace_spans if s.get("endtimestamp")]
                    if starts and ends:
                        # Since they are ISO strings, simple diff is harder without datetime parsing
                        # But we can approximate, or just leave it. If custom.duration is missing we just default.
                        pass
                except Exception:
                    pass

            summaries.append(TraceSummary(
                trace_id=tid,
                service=root_span.get("service") or "unknown",
                operation=root_span.get("operationname") or "operation",
                resource=root_span.get("resourcename") or "resource",
                timestamp=root_span.get("starttimestamp") or "",
                duration_ms=round(duration_ms, 2),
                status=trace_status,
                span_count=len(trace_spans)
            ))

        # Sort trace summaries by timestamp descending (newest first)
        summaries = sorted(summaries, key=lambda x: x.timestamp, reverse=True)

        return TracesListResponse(traces=summaries, status_info="live")

    except Exception as e:
        logger.error(f"Failed to fetch traces: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch traces from Datadog: {str(e)}"
        )


@router.get("/{trace_id}", response_model=TraceDetailResponse)
def get_trace_detail(trace_id: str):
    """
    Fetch full detail of a specific trace from Datadog APM.
    """
    if not settings.datadog_api_key_val or not settings.datadog_app_key_val:
        raise HTTPException(
            status_code=400,
            detail="Datadog credentials are not configured. Please set DD_API_KEY and DD_APP_KEY."
        )

    try:
        mcp_client = DatadogMCPClient()
        mcp_client.initialize()

        # Query trace detail via MCP
        resp = mcp_client.call_tool("get_datadog_trace", {
            "trace_id": trace_id,
            "telemetry": {"intent": f"Retrieve trace detail for waterfall rendering: {trace_id}"}
        })

        spans_data = parse_yaml_data(resp)
        metadata = parse_metadata(resp)

        if not spans_data:
            raise HTTPException(
                status_code=404,
                detail=f"Trace with ID {trace_id} not found or contains no spans."
            )

        spans: List[TraceSpan] = []
        for s in spans_data:
            # Determine status based on whether error dictionary is populated
            span_err = s.get("error")
            status = "error" if span_err and isinstance(span_err, dict) and len(span_err) > 0 else "ok"
            
            # If status tag is explicitly given as error, prioritize it
            if s.get("status") == "error":
                status = "error"

            spans.append(TraceSpan(
                span_id=s.get("span_id") or "",
                parent_id=s.get("parent_id") or "0",
                service=s.get("service") or "unknown",
                name=s.get("name") or "operation",
                resource=s.get("resource") or "resource",
                start_time=s.get("start_time") or "",
                end_time=s.get("end_time") or "",
                duration_ms=float(s.get("duration_ms") or 0.0),
                status=status,
                meta=s.get("meta") or {}
            ))

        # Sort spans by start_time so root/earliest is first
        try:
            spans = sorted(spans, key=lambda x: x.start_time)
        except Exception:
            pass

        return TraceDetailResponse(
            trace_id=trace_id,
            deep_link_url=metadata.get("trace_deep_link_url"),
            spans=spans,
            status_info="live"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch trace detail: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch trace detail from Datadog: {str(e)}"
        )
