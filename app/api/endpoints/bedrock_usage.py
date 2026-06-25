import json
import logging
from typing import List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.utils.ddstarter.mcp_client import DatadogMCPClient

logger = logging.getLogger(__name__)
router = APIRouter()


class BedrockInvocation(BaseModel):
    model_config = {"protected_namespaces": ()}
    timestamp: str
    model_id: str
    latency_ms: float
    input_tokens: int
    output_tokens: int
    status: str


class BedrockModelUsage(BaseModel):
    model_config = {"protected_namespaces": ()}
    model_id: str
    invocation_count: int
    avg_latency_ms: float
    total_input_tokens: int
    total_output_tokens: int


class BedrockUsageResponse(BaseModel):
    model_config = {"protected_namespaces": ()}
    total_invocations: int
    total_tokens: int
    avg_latency_ms: float
    error_rate: float
    models: List[BedrockModelUsage]
    recent_invocations: List[BedrockInvocation]


def _get_client() -> DatadogMCPClient:
    client = DatadogMCPClient()
    client.initialize()
    return client


def _parse_spans(raw: str) -> List[dict]:
    try:
        data = json.loads(raw) if raw else []
        return data if isinstance(data, list) else data.get("spans", data.get("data", []))
    except (json.JSONDecodeError, AttributeError):
        return []


def _build_invocations(spans: list) -> List[BedrockInvocation]:
    invocations = []
    for span in spans:
        meta = span.get("meta", span.get("attributes", {}))
        invocations.append(BedrockInvocation(
            timestamp=str(span.get("start", span.get("timestamp", ""))),
            model_id=meta.get("model_id", meta.get("aws.bedrock.model_id", "unknown")),
            latency_ms=float(span.get("duration", 0)) / 1_000_000,
            input_tokens=int(meta.get("input_tokens", meta.get("aws.bedrock.input_tokens", 0))),
            output_tokens=int(meta.get("output_tokens", meta.get("aws.bedrock.output_tokens", 0))),
            status="error" if span.get("error", 0) == 1 else "ok",
        ))
    return invocations


def _aggregate(invocations: List[BedrockInvocation]) -> BedrockUsageResponse:
    model_map: dict = {}
    errors = sum(1 for i in invocations if i.status == "error")

    for inv in invocations:
        entry = model_map.setdefault(inv.model_id, {"count": 0, "latency_sum": 0.0, "in_tok": 0, "out_tok": 0})
        entry["count"] += 1
        entry["latency_sum"] += inv.latency_ms
        entry["in_tok"] += inv.input_tokens
        entry["out_tok"] += inv.output_tokens

    models = [
        BedrockModelUsage(
            model_id=mid,
            invocation_count=d["count"],
            avg_latency_ms=round(d["latency_sum"] / d["count"], 2) if d["count"] else 0,
            total_input_tokens=d["in_tok"],
            total_output_tokens=d["out_tok"],
        )
        for mid, d in model_map.items()
    ]

    total = len(invocations)
    total_tokens = sum(i.input_tokens + i.output_tokens for i in invocations)
    avg_lat = round(sum(i.latency_ms for i in invocations) / total, 2) if total else 0

    return BedrockUsageResponse(
        total_invocations=total,
        total_tokens=total_tokens,
        avg_latency_ms=avg_lat,
        error_rate=round(errors / total, 4) if total else 0,
        models=models,
        recent_invocations=invocations[:50],
    )


@router.get("/", response_model=BedrockUsageResponse)
def get_bedrock_usage():
    """Fetch AWS Bedrock usage data from Datadog MCP."""
    try:
        client = _get_client()
        raw_spans = client.call_tool("search_datadog_spans", {"query": "service:aws.bedrock", "limit": 200})
        invocations = _build_invocations(_parse_spans(raw_spans))
        return _aggregate(invocations)
    except Exception as e:
        logger.error(f"Failed to fetch bedrock usage: {e}")
        raise HTTPException(status_code=502, detail=f"Datadog MCP error: {str(e)}")


@router.get("/models", response_model=List[BedrockModelUsage])
def get_bedrock_models():
    """Get per-model breakdown of AWS Bedrock usage."""
    try:
        client = _get_client()
        raw_spans = client.call_tool("search_datadog_spans", {"query": "service:aws.bedrock", "limit": 200})
        invocations = _build_invocations(_parse_spans(raw_spans))
        return _aggregate(invocations).models
    except Exception as e:
        logger.error(f"Failed to fetch bedrock model usage: {e}")
        raise HTTPException(status_code=502, detail=f"Datadog MCP error: {str(e)}")
