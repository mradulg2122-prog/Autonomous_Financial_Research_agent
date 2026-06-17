"""
ARA-1 Prometheus Metrics
Application-level counters, histograms, and gauges.
"""
from __future__ import annotations

from prometheus_client import Counter, Histogram, Gauge, Info

# ── Research Session Metrics ───────────────────────────────────
research_sessions_total = Counter(
    "ara1_research_sessions_total",
    "Total number of research sessions started",
    ["status"],  # labels: pending, complete, failed
)

research_duration_seconds = Histogram(
    "ara1_research_duration_seconds",
    "Duration of research sessions in seconds",
    buckets=[30, 60, 120, 180, 300, 600, 900, 1800],
)

# ── Agent Metrics ──────────────────────────────────────────────
agent_executions_total = Counter(
    "ara1_agent_executions_total",
    "Total number of agent executions",
    ["agent_name", "status"],
)

agent_duration_ms = Histogram(
    "ara1_agent_duration_ms",
    "Agent execution duration in milliseconds",
    ["agent_name"],
    buckets=[500, 1000, 2000, 5000, 10000, 30000, 60000],
)

# ── Tool Metrics ───────────────────────────────────────────────
tool_calls_total = Counter(
    "ara1_tool_calls_total",
    "Total number of tool invocations",
    ["tool_name", "success"],
)

tool_duration_ms = Histogram(
    "ara1_tool_duration_ms",
    "Tool execution duration in milliseconds",
    ["tool_name"],
    buckets=[100, 500, 1000, 2000, 5000, 10000, 30000],
)

# ── LLM Metrics ────────────────────────────────────────────────
llm_requests_total = Counter(
    "ara1_llm_requests_total",
    "Total number of OpenAI API requests",
    ["model", "endpoint"],
)

llm_tokens_total = Counter(
    "ara1_llm_tokens_total",
    "Total number of tokens used",
    ["model", "token_type"],  # token_type: prompt, completion
)

llm_cost_dollars = Counter(
    "ara1_llm_cost_dollars_total",
    "Estimated total LLM API cost in USD",
)

# ── Memory Metrics ─────────────────────────────────────────────
vector_operations_total = Counter(
    "ara1_vector_operations_total",
    "Total Qdrant vector DB operations",
    ["operation"],  # store, search
)

redis_operations_total = Counter(
    "ara1_redis_operations_total",
    "Total Redis operations",
    ["operation"],  # get, set, delete
)

# ── Report & Evaluation Metrics ────────────────────────────────
reports_generated_total = Counter(
    "ara1_reports_generated_total",
    "Total number of research reports generated",
)

evaluation_scores = Histogram(
    "ara1_evaluation_scores",
    "Distribution of evaluation overall scores",
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
)

# ── System Gauges ──────────────────────────────────────────────
active_sessions_gauge = Gauge(
    "ara1_active_sessions",
    "Number of currently running research sessions",
)

websocket_connections_gauge = Gauge(
    "ara1_websocket_connections",
    "Number of active WebSocket connections",
)

# ── Service Info ───────────────────────────────────────────────
service_info = Info(
    "ara1_service",
    "ARA-1 service metadata",
)
service_info.info({
    "version": "1.0.0",
    "agents": "9",
    "tools": "15",
    "memory_backends": "redis,qdrant,postgresql",
})
