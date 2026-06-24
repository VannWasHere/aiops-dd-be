import datetime
import random
from sqlalchemy.orm import Session
from app.models.investigation import Investigation
from app.models.investigation_timeline import InvestigationTimeline
from app.models.recommendation import Recommendation
from app.models.evidence import Evidence
from app.models.service import Service

# Pre-defined realistic incident templates
SCENARIOS = [
    {
        "keywords": ["pool", "db", "database", "connection", "postgres", "sql"],
        "summary": "Database connection pool exhaustion on the main database instance.",
        "root_cause": "A sudden burst of read/write requests, combined with unindexed search queries in a recent deployment, locked tables and exhausted the database client pool size limit (set to 20). Upstream services backed up and started timing out.",
        "timeline": [
            {"offset_min": -60, "title": "Deployment Finished", "description": "Version v1.4.12 of the service deployed to production."},
            {"offset_min": -45, "title": "Database CPU Spike", "description": "Database CPU usage spiked from 15% to 98% due to unindexed queries on table 'orders'."},
            {"offset_min": -35, "title": "Connection Pool Limit Reached", "description": "Service instances reported 'sqlalchemy.exc.TimeoutError: QueuePool limit of size 20 overflow 10 reached'."},
            {"offset_min": -30, "title": "Latency Spike Alert", "description": "APM reported average latency rose above the 2000ms threshold (P99 at 8500ms)."},
            {"offset_min": -20, "title": "HTTP 500 Spike Alert", "description": "PagerDuty triggered alert for HTTP 500 error rates exceeding 5% on checkout endpoint."}
        ],
        "recommendations": [
            {"title": "Optimize SQL Queries", "description": "Identify unindexed columns on the 'orders' table and add composite indexes to speed up lookup times.", "priority": "High"},
            {"title": "Increase Connection Pool Size", "description": "Adjust pool_size to 50 and max_overflow to 20 in database.py configuration.", "priority": "Medium"},
            {"title": "Implement Database Read Replicas", "description": "Redirect heavy read queries to a read-only replica to reduce load on the primary DB.", "priority": "Low"}
        ],
        "evidence": [
            {"source": "Datadog APM Traces", "details": "APM trace logs show db.connection.acquire_time averaging 4.2 seconds per request during the outage."},
            {"source": "Postgres Pg_Stat_Statements", "details": "Query logs show SELECT * FROM orders WHERE status = 'PENDING' AND owner_id = ? taking over 800ms per call without indexes."},
            {"source": "Container Logs", "details": "Stdout logs contain 342 instances of 'QueuePool limit of size 20 overflow 10 reached' exceptions."}
        ]
    },
    {
        "keywords": ["memory", "leak", "oom", "crash", "restart", "heap"],
        "summary": "Memory leak leading to container Out-Of-Memory (OOM) kills and continuous restarts.",
        "root_cause": "A file handler stream in the file upload middleware was not properly closed inside an exception block. Over time, memory usage grew linearly until hitting the Kubernetes container limit, causing OOM kills.",
        "timeline": [
            {"offset_min": -180, "title": "Linear Memory Growth", "description": "Grafana metrics show service memory usage growing steadily by 12MB/minute after v2.1.0 release."},
            {"offset_min": -40, "title": "Container Out-Of-Memory (OOM)", "description": "Kubernetes node terminated the primary pod with exit code 137 (OOMKilled)."},
            {"offset_min": -35, "title": "Pod Restarts Loop", "description": "The secondary pod also reached limit and crashed, starting a restart loop and reducing service capacity to 0%."},
            {"offset_min": -30, "title": "Availability Alert Fired", "description": "Synthetic API pingers failed, firing critical alert for 100% packet loss on healthcheck."},
            {"offset_min": -10, "title": "Traffic Auto-routed", "description": "Cloudflare automatically routed 50% of the traffic to the fallback region."}
        ],
        "recommendations": [
            {"title": "Fix File Stream Closing", "description": "Wrap file uploads in a 'with' block or ensure 'stream.close()' is executed in a finally block.", "priority": "High"},
            {"title": "Adjust Kubernetes Memory Limits", "description": "Temporarily increase memory limits from 1Gi to 2Gi to give the container more headroom.", "priority": "Medium"},
            {"title": "Add Heap Profiling", "description": "Configure Prometheus client or Datadog profiler to track memory allocations by class type.", "priority": "Low"}
        ],
        "evidence": [
            {"source": "Kubernetes Events", "details": "Kubelet event log: 'Pod checkout-api-7d6f54c9c-2x8pl Container checkout-api web crashed: OOMKilled (Exit Code 137)'"},
            {"source": "Prometheus Node Exporter", "details": "Memory usage chart shows a clear saw-tooth pattern with steep drops coinciding with container restarts."},
            {"source": "Middleware Trace", "details": "Heap dump analysis points to 14,200 open instances of BytesIO streams holding uncompressed image byte arrays."}
        ]
    },
    {
        "keywords": ["payment", "gateway", "stripe", "external", "third-party", "timeout", "network"],
        "summary": "External payment gateway latency spike and socket timeouts.",
        "root_cause": "The payment provider's sandbox API experienced a massive outage, causing our outgoing HTTP requests to block indefinitely because no timeout limits were configured in the Axios/HTTP client.",
        "timeline": [
            {"offset_min": -90, "title": "External Provider Outage", "description": "Payment Gateway reports a DNS failure and high latency on their endpoint /v1/charges."},
            {"offset_min": -75, "title": "Thread Pool Depletion", "description": "Our checkout-api service became unresponsive as all threads were blocked waiting on network responses from payment gateway."},
            {"offset_min": -60, "title": "Timeout Exception Triggered", "description": "Upstream reverse proxy (Nginx) began returning 504 Gateway Timeout responses to users."},
            {"offset_min": -45, "title": "Alarm Fired", "description": "P99 HTTP response time spiked from 120ms to 30000ms (30 seconds limit)."}
        ],
        "recommendations": [
            {"title": "Configure HTTP Client Timeouts", "description": "Enforce a strict 5-second socket timeout on all outgoing external HTTP requests.", "priority": "High"},
            {"title": "Implement Circuit Breaker Pattern", "description": "Introduce a circuit breaker (e.g., PyBreaker) to immediately fail fast if the gateway has more than 5 consecutive timeouts.", "priority": "High"},
            {"title": "Provide User-Friendly Error Messages", "description": "Gracefully inform the user of payment service delays instead of freezing the checkout checkout interface.", "priority": "Medium"}
        ],
        "evidence": [
            {"source": "External Status Page", "details": "Stripe/Adyen incident log: 'API Latency Spikes in EU-West regions between 14:00 and 15:30 UTC.'"},
            {"source": "HTTP Request Logs", "details": "Outgoing request logs show 832 checkout calls pending for exactly 60.00 seconds before being closed by client browser resets."},
            {"source": "Nginx Log Analysis", "details": "504 Gateway Timeout error count spiked to 1,234 within a 15-minute window."}
        ]
    }
]

DEFAULT_SCENARIO = {
    "summary": "Sudden latency increase and error spike following code change.",
    "root_cause": "A recent code change in the main controller added a sequential loop of external API metadata lookups instead of performing a batch query. This multiplied network roundtrips by the number of returned items (N+1 query problem).",
    "timeline": [
        {"offset_min": -45, "title": "Code Release", "description": "New feature branch containing user metadata aggregation merged and deployed."},
        {"offset_min": -30, "title": "Latency Escalation", "description": "Response time for user profile details rose from 45ms to 1250ms."},
        {"offset_min": -25, "title": "APM Alerts Fired", "description": "High response time warning alert triggered for user-api service."},
        {"offset_min": -15, "title": "Error Rate Spike", "description": "Timeout errors on dependent microservices reached critical thresholds."}
    ],
    "recommendations": [
        {"title": "Refactor sequential calls to batch calls", "description": "Replace the sequential loop with a single bulk fetch database query or network request.", "priority": "High"},
        {"title": "Implement Redis Caching", "description": "Cache user metadata objects in Redis with a 5-minute TTL to reduce database roundtrips.", "priority": "Medium"},
        {"title": "Review PR Guidelines", "description": "Add mandatory checklists for loops containing DB queries or API requests to prevent N+1 issues.", "priority": "Low"}
    ],
    "evidence": [
        {"source": "APM Trace Profiler", "details": "APM flame graph shows 125 database fetch operations executed sequentially within a single request context."},
        {"source": "Database Query Counters", "details": "Database queries per second (QPS) increased from 400 to 2,800 immediately following the deployment."},
        {"source": "AWS CloudWatch Metrics", "details": "CPU usage on the RDS cluster rose by 35% without an increase in user sessions."}
    ]
}

def generate_investigation_details(db: Session, investigation: Investigation, service_name: str):
    # Find matching scenario
    text_to_search = (investigation.title + " " + investigation.question).lower()
    scenario = DEFAULT_SCENARIO
    for s in SCENARIOS:
        if any(keyword in text_to_search for keyword in s["keywords"]) or any(keyword in service_name.lower() for keyword in s["keywords"]):
            scenario = s
            break
    
    # Update investigation object with summary and root cause
    investigation.summary = f"({service_name}) {scenario['summary']}"
    investigation.root_cause = scenario["root_cause"]
    investigation.status = "investigating"
    db.commit()

    # Generate timeline
    base_time = datetime.datetime.utcnow()
    for item in scenario["timeline"]:
        event_time = base_time + datetime.timedelta(minutes=item["offset_min"])
        timeline_event = InvestigationTimeline(
            investigation_id=investigation.id,
            event_time=event_time,
            title=item["title"],
            description=item["description"]
        )
        db.add(timeline_event)

    # Generate recommendations
    for item in scenario["recommendations"]:
        rec = Recommendation(
            investigation_id=investigation.id,
            title=item["title"],
            description=item["description"],
            priority=item["priority"]
        )
        db.add(rec)

    # Generate evidence
    for item in scenario["evidence"]:
        ev = Evidence(
            investigation_id=investigation.id,
            source=item["source"],
            details=item["details"]
        )
        db.add(ev)

    db.commit()
    db.refresh(investigation)
    return investigation
