import json
import re
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
import boto3
import yaml
import requests as http_requests

from app.core.config import settings
from app.core.database import get_db
from app.models.investigation import Investigation
from app.models.investigation_timeline import InvestigationTimeline
from app.models.recommendation import Recommendation
from app.models.evidence import Evidence
from app.models.service import Service
import datetime
import uuid

logger = logging.getLogger(__name__)
router = APIRouter()


# --- Helpers ---

def _mcp_call(tool_name: str, arguments: dict) -> str:
    api_key = settings.datadog_api_key_val
    app_key = settings.datadog_app_key_val
    mcp_url = settings.mcp_server_url_val or "https://mcp.datadoghq.com/v1/mcp?toolsets=all"
    if not api_key or not app_key:
        raise ValueError("DD_API_KEY and DD_APP_KEY required")
    headers = {"Content-Type": "application/json", "DD-API-KEY": api_key, "DD-APPLICATION-KEY": app_key, "Accept": "application/json, text/event-stream"}
    resp = http_requests.post(mcp_url, json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "aiops-investigator", "version": "1.0"}}}, headers=headers, timeout=15)
    headers["Mcp-Session-Id"] = resp.headers.get("Mcp-Session-Id", "")
    resp2 = http_requests.post(mcp_url, json={"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": tool_name, "arguments": arguments}}, headers=headers, timeout=30)
    data = resp2.json()
    content = data.get("result", {}).get("content", [])
    return content[0].get("text", "") if content else ""


def _ask_bedrock(prompt: str) -> str:
    model_id = settings.BEDROCK_MODEL_ID or "amazon.nova-pro-v1:0"
    region = settings.AWS_REGION or "us-east-1"
    client = boto3.client("bedrock-runtime", region_name=region,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None)
    response = client.invoke_model(
        modelId=model_id,
        body=json.dumps({"messages": [{"role": "user", "content": [{"text": prompt}]}], "inferenceConfig": {"max_new_tokens": 2048}}),
        contentType="application/json")
    result_body = json.loads(response["body"].read())
    return result_body["output"]["message"]["content"][0]["text"]


# --- Models ---

class DetectedError(BaseModel):
    trace_id: str
    service: str
    operation: str
    resource: str
    timestamp: str
    error_message: str = ""


class AutoDetectResponse(BaseModel):
    errors_found: int
    investigations_created: List[str]
    errors: List[DetectedError]


class GenerateScriptResponse(BaseModel):
    investigation_id: str
    script: str
    language: str
    description: str


# --- Endpoints ---

@router.post("/auto-detect", response_model=AutoDetectResponse)
def auto_detect_errors(db: Session = Depends(get_db)):
    """
    Scan Datadog for error traces via MCP, and auto-generate investigations
    with Bedrock-powered root cause analysis and remediation scripts.
    """
    # Fetch error spans from MCP
    try:
        raw = _mcp_call("search_datadog_spans", {"query": "status:error", "from": "now-1h"})
        # Parse YAML_DATA from MCP response
        yaml_match = re.search(r'<YAML_DATA>(.*?)</YAML_DATA>', raw, re.DOTALL)
        if yaml_match:
            spans = yaml.safe_load(yaml_match.group(1).strip()) or []
        else:
            try:
                spans = json.loads(raw) if raw else []
            except (json.JSONDecodeError, TypeError):
                spans = yaml.safe_load(raw) if raw else []
        if not isinstance(spans, list):
            spans = spans.get("spans", spans.get("data", []))
    except Exception as e:
        logger.error(f"MCP error scan failed: {e}")
        raise HTTPException(status_code=502, detail=f"MCP error: {str(e)}")

    if not spans:
        return AutoDetectResponse(errors_found=0, investigations_created=[], errors=[])

    # Group errors by service
    service_errors: dict = {}
    detected: List[DetectedError] = []
    for span in spans[:50]:
        svc = span.get("service", "unknown")
        custom = span.get("custom", {})
        err_msg = ""
        if isinstance(custom, dict):
            err = custom.get("error", {})
            if isinstance(err, dict):
                err_msg = err.get("message", err.get("msg", ""))
            # Also check http status code
            http_info = custom.get("http", {})
            if isinstance(http_info, dict) and not err_msg:
                status_code = http_info.get("status_code", "")
                err_msg = f"HTTP {status_code}" if status_code else ""
        op = span.get("resourcename", span.get("operationname", ""))
        resource = span.get("resourcename", "")
        tid = str(span.get("traceid", ""))
        ts = str(span.get("starttimestamp", ""))

        detected.append(DetectedError(trace_id=tid, service=svc, operation=op, resource=resource, timestamp=ts, error_message=str(err_msg)[:200]))

        if svc not in service_errors:
            service_errors[svc] = []
        service_errors[svc].append({"operation": op, "resource": resource, "error": str(err_msg)[:300], "timestamp": ts})

    # For each service with errors, create an investigation with Bedrock analysis
    created_ids: List[str] = []
    
    # Get first available service from DB (or create a default)
    db_service = db.query(Service).first()
    if not db_service:
        db_service = Service(name="auto-detected", description="Auto-detected service", environment="production", owner="AI-Ops", status="degraded")
        db.add(db_service)
        db.commit()
        db.refresh(db_service)

    for svc_name, errors in list(service_errors.items())[:3]:  # Limit to 3 investigations
        error_summary = "\n".join([f"- [{e['operation']}] {e['resource']}: {e['error']}" for e in errors[:10]])

        # Ask Bedrock for RCA + remediation script
        prompt = f"""You are an expert SRE engineer. Analyze these error traces from service '{svc_name}' and provide:

1. A brief SUMMARY (2-3 sentences) of the issue
2. ROOT CAUSE analysis (detailed technical explanation)
3. REMEDIATION SCRIPT (a bash or python script that fixes or mitigates the issue)
4. TIMELINE of what likely happened (3-5 events)
5. Three RECOMMENDATIONS with priorities (High/Medium/Low)

Errors detected:
{error_summary}

Format your response as JSON:
{{
  "summary": "...",
  "root_cause": "...",
  "remediation_script": "...",
  "script_language": "bash|python",
  "timeline": [{{"title": "...", "description": "..."}}],
  "recommendations": [{{"title": "...", "description": "...", "priority": "High|Medium|Low"}}]
}}"""

        try:
            bedrock_response = _ask_bedrock(prompt)
            # Parse JSON from response (handle markdown code blocks)
            json_str = bedrock_response
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0]
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0]
            analysis = json.loads(json_str.strip())
        except Exception as e:
            logger.warning(f"Bedrock analysis failed for {svc_name}: {e}")
            analysis = {
                "summary": f"Detected {len(errors)} errors in service {svc_name}. Automated analysis unavailable.",
                "root_cause": f"Multiple error spans detected: {error_summary[:500]}",
                "remediation_script": f"#!/bin/bash\n# Auto-generated remediation placeholder\necho 'Restart service {svc_name}'\n# kubectl rollout restart deployment/{svc_name}",
                "script_language": "bash",
                "timeline": [{"title": "Errors Detected", "description": f"{len(errors)} error spans found in the last hour"}],
                "recommendations": [{"title": "Investigate Error Logs", "description": f"Review detailed error logs for {svc_name}", "priority": "High"}]
            }

        # Create investigation in DB
        inv = Investigation(
            service_id=db_service.id,
            title=f"Auto-detected: {svc_name} errors ({len(errors)} spans)",
            question=f"Automated error detection found {len(errors)} error traces in service '{svc_name}'. Errors: {error_summary[:500]}",
            status="investigating",
            summary=analysis.get("summary", ""),
            root_cause=analysis.get("root_cause", "")
        )
        db.add(inv)
        db.commit()
        db.refresh(inv)

        # Add timeline
        now = datetime.datetime.utcnow()
        for i, t in enumerate(analysis.get("timeline", [])[:5]):
            tl = InvestigationTimeline(
                investigation_id=inv.id,
                event_time=now - datetime.timedelta(minutes=(5 - i) * 10),
                title=t.get("title", "Event"),
                description=t.get("description", "")
            )
            db.add(tl)

        # Add recommendations (include remediation script as first recommendation)
        script = analysis.get("remediation_script", "")
        script_lang = analysis.get("script_language", "bash")
        if script:
            rec_script = Recommendation(
                investigation_id=inv.id,
                title="REMEDIATION SCRIPT",
                description=f"```{script_lang}\n{script}\n```",
                priority="High"
            )
            db.add(rec_script)

        for r in analysis.get("recommendations", [])[:5]:
            rec = Recommendation(
                investigation_id=inv.id,
                title=r.get("title", "Fix"),
                description=r.get("description", ""),
                priority=r.get("priority", "Medium")
            )
            db.add(rec)

        # Add evidence
        ev = Evidence(
            investigation_id=inv.id,
            source="Datadog MCP Error Traces",
            details=error_summary
        )
        db.add(ev)

        if script:
            ev_script = Evidence(
                investigation_id=inv.id,
                source=f"AI-Generated Remediation ({script_lang})",
                details=script
            )
            db.add(ev_script)

        db.commit()
        created_ids.append(str(inv.id))

    return AutoDetectResponse(errors_found=len(detected), investigations_created=created_ids, errors=detected[:20])


@router.post("/{investigation_id}/generate-script", response_model=GenerateScriptResponse)
def generate_fix_script(investigation_id: str, db: Session = Depends(get_db)):
    """Generate a remediation script for an existing investigation using Bedrock."""
    inv = db.query(Investigation).filter(Investigation.id == investigation_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Investigation not found")

    prompt = f"""You are an expert SRE/DevOps engineer. Generate a production-ready remediation script for this incident:

Title: {inv.title}
Summary: {inv.summary}
Root Cause: {inv.root_cause}
Original Query: {inv.question}

Generate a complete, executable remediation script (bash or python) that:
1. Diagnoses the current state
2. Applies the fix
3. Verifies the fix worked
4. Has error handling and rollback capability

Return ONLY the script with comments, no additional text. Start with a shebang line."""

    try:
        script = _ask_bedrock(prompt)
        # Clean markdown if present
        if script.startswith("```"):
            lines = script.split("\n")
            lang = lines[0].replace("```", "").strip() or "bash"
            script = "\n".join(lines[1:])
            if script.endswith("```"):
                script = script[:-3]
        else:
            lang = "bash" if script.strip().startswith("#!/bin/bash") else "python"
    except Exception as e:
        logger.error(f"Script generation failed: {e}")
        raise HTTPException(status_code=502, detail=f"Bedrock error: {str(e)}")

    # Save script as evidence
    ev = Evidence(
        investigation_id=inv.id,
        source=f"AI-Generated Fix Script ({lang})",
        details=script
    )
    db.add(ev)
    db.commit()

    return GenerateScriptResponse(
        investigation_id=investigation_id,
        script=script,
        language=lang,
        description=f"Remediation script for: {inv.title}"
    )
