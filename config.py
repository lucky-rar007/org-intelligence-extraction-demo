"""Global configuration settings for the Organizational Event Intelligence Pipeline.

This module acts as the single source of truth for all application configuration,
including paths, local model hosts, parameter thresholds, and logging settings.
"""

from pathlib import Path

# =====================================================================
# PROJECT PATHS
# =====================================================================

BASE_DIR = Path(__file__).resolve().parent

# Data directories
DATA_DIR = BASE_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"

# Prompt directories
PROMPTS_DIR = BASE_DIR / "prompts"

# Output directories
OUTPUTS_DIR = BASE_DIR / "outputs"
EVENTS_OUTPUT_DIR = OUTPUTS_DIR / "events"
OBSERVATIONS_OUTPUT_DIR = OUTPUTS_DIR / "observations"
ISSUES_OUTPUT_DIR = OUTPUTS_DIR / "issues"
CLUSTERS_OUTPUT_DIR = OUTPUTS_DIR / "clusters"
REPORTS_OUTPUT_DIR = OUTPUTS_DIR / "reports"
LOGS_OUTPUT_DIR = OUTPUTS_DIR / "logs"

# =====================================================================
# OLLAMA CONFIGURATION
# =====================================================================

OLLAMA_HOST: str = "http://localhost:11434"
OLLAMA_BASE_URL: str = OLLAMA_HOST
OLLAMA_MODEL: str = "llama3.1:8b-instruct"
OLLAMA_TIMEOUT_SECONDS: int = 120
OLLAMA_TEMPERATURE: float = 0.0


# =====================================================================
#  EVENT EXTRACTION SETTINGS
# =====================================================================

MIN_EVENT_CONFIDENCE: float = 0.70
MAX_EVENTS_PER_BATCH: int = 50

# =====================================================================
# EVENT FILTER SETTINGS
# =====================================================================

# Event types that are always classified as actionable Events (never Observations)
EVENT_FILTER_ACTIONABLE_TYPES: list[str] = [
    "CLIENT_ESCALATION",
    "PRODUCTION_INCIDENT",
    "DELIVERY_BLOCKED",
    "RELEASE_DELAY",
    "INFRASTRUCTURE_ISSUE",
    "PERFORMANCE_DEGRADATION",
]

# Mappings of high-level root-cause categories to list of keywords for clustering
CLUSTER_KEYWORD_MAPPINGS: dict[str, list[str]] = {
    "Payment Gateway": ["payment gateway", "paytm", "checkout", "gateway"],
    "Webhook Systems": ["webhook"],
    "Redis Cache": ["redis"],
    "Staging Database": ["staging database", "staging db", "connection pool"],
    "Android App": ["android app", "android", "proguard", "mobile"],
    "iOS App": ["ios app", "ios"],
    "Client ABC": ["client abc"],
    "Client XYZ": ["client xyz"],
}

# Known engineering/team member first names for normalization and tracking
KNOWN_TEAM_NAMES: list[str] = ["Siddharth", "Ananya", "Karan", "Neha", "Rohan"]

# =====================================================================
# OBSERVATION SETTINGS
# =====================================================================

OBSERVATION_AGGREGATION_THRESHOLD: int = 2
"""Minimum observation occurrences before generating an intelligence finding."""

# =====================================================================
# ISSUE TRACKING SETTINGS
# =====================================================================

ISSUE_MATCH_THRESHOLD: float = 0.85

# =====================================================================
# REPORT GENERATION SETTINGS
# =====================================================================

MAX_CRITICAL_ISSUES: int = 10
MAX_EXECUTIVE_FINDINGS: int = 5

# =====================================================================
#LOGGING SETTINGS
# =====================================================================

LOG_LEVEL: str = "INFO"


# =====================================================================
# ISSUE LIFECYCLE SETTINGS (Phase 1)
# =====================================================================

RESOLUTION_SIMILARITY_THRESHOLD: float = 0.65
"""Lower threshold than ISSUE_MATCH_THRESHOLD to catch resolution events
that reference existing issues with slightly different wording."""

ESCALATION_DAYS_THRESHOLD_1: int = 3
"""Days an issue must be open before first attention escalation."""

ESCALATION_DAYS_THRESHOLD_2: int = 7
"""Days an issue must be open before second attention escalation."""

# Keywords that indicate an event is a resolution or fix confirmation
RESOLUTION_KEYWORDS: list[str] = [
    "resolved", "fixed", "patched", "verified", "working now",
    "closed", "completed", "deployed successfully", "issue gone",
    "validated", "confirmed fixed", "merged and deployed",
    "root cause addressed", "production stable", "staging healthy",
    "refunds completed", "tickets closed", "successfully deployed",
    "hotfix deployed", "patch deployed", "fix confirmed",
    "working as expected", "issue resolved", "bug fixed",
    "sign-off received", "qa passed", "production verified",
    "sanity test passed", "build successful", "deployed to production",
]

# Keywords that indicate transition to MONITORING (fix in progress, not confirmed)
MONITORING_KEYWORDS: list[str] = [
    "patch deployed", "fix merged", "testing in progress",
    "awaiting qa validation", "monitoring production",
    "deployed to staging", "fix pushed", "hotfix merged",
    "under observation", "waiting for verification",
    "regression testing", "canary deployment",
    "rolling out", "fix in progress", "build generated",
    "ready for publication", "awaiting confirmation",
    "hotfix release", "release to production",
    "deployed to production", "monitoring database",
    "monitoring connections", "uploaded to",
    "published to", "release deployed",
]


# =====================================================================
# FOUNDER CLASSIFICATION SETTINGS (Phase 2)
# =====================================================================

# Keywords mapped to FounderImpact categories for deterministic classification
FOUNDER_IMPACT_KEYWORDS: dict[str, list[str]] = {
    "REVENUE_RISK": [
        "revenue", "billing", "payment", "invoice", "subscription",
        "charge", "double charge", "refund", "transaction",
        "pricing", "monetization", "lost account", "churn",
        "paytm", "gateway", "checkout",
    ],
    "CUSTOMER_RISK": [
        "client escalation", "customer complaint", "client dissatisfied",
        "customer churn", "client abc", "client xyz", "account manager",
        "client unhappy", "sla breach", "support ticket",
        "customer support", "client request", "client feedback",
        "client demo", "client wireframe", "exports tab",
        "feature flag", "dashboard data stale",
    ],
    "DELIVERY_RISK": [
        "deployment blocked", "deployment delay", "release delay",
        "delivery blocked", "sprint delay", "deadline missed",
        "deployment failed", "release blocked", "build failed",
        "build failure", "merge conflict", "qa queue",
        "regression", "blocker", "blocked",
    ],
    "OPERATIONAL_RISK": [
        "production incident", "outage", "downtime", "infrastructure",
        "database", "cpu spike", "disk space", "memory", "server",
        "aws", "ecr", "cloud", "network", "dns", "ssl",
        "connection pool", "502", "500", "timeout", "latency",
        "caching", "redis", "staging", "cors", "csp",
    ],
    "TEAM_RISK": [
        "burnout", "team conflict", "capacity", "overloaded",
        "understaffed", "morale", "attrition", "resignation",
    ],
    "HIRING_RISK": [
        "hiring", "recruitment", "staffing", "open position",
        "headcount", "talent", "candidate",
    ],
    "STRATEGIC_RISK": [
        "roadmap", "pivot", "strategy", "partnership",
        "acquisition", "market", "competitor", "board",
    ],
    "COMPLIANCE_RISK": [
        "compliance", "regulatory", "audit", "gdpr",
        "security", "vulnerability", "data breach",
    ],
    "PRODUCT_RISK": [
        "proguard", "crash", "crash log", "ux", "ui regression",
        "feature regression", "android", "ios", "mobile",
        "login issue", "sdk integration", "app crash",
    ],
}

# Noise keywords for social/irrelevant conversations
NOISE_KEYWORDS: list[str] = [
    "eatfit", "toit", "dinner", "lunch", "breakfast",
    "cricket", "movie", "movies", "birthday", "restaurant",
    "food order", "social", "weekend", "drinks", "party",
    "joke", "meme", "greeting", "good morning", "good night",
    "happy birthday", "tea break", "coffee break",
]

# Team-level keywords (relevant but not founder-level)
TEAM_LEVEL_KEYWORDS: list[str] = [
    "frontend bug", "css issue", "environment setup",
    "credential request", "local build", "staging-only",
    "single ticket", "routine", "estimate", "status update",
    "standup", "sprint board", "ticket update", "follow up",
    "documentation", "wiki", "readme", "postman",
    "dark mode", "design concept", "wireframe",
    "unit test", "code review", "pr review", "merge request",
]


# =====================================================================
# FILE CREATION HELPER
# =====================================================================

def create_required_directories() -> None:
    """Create all required project directories if they do not exist."""
    directories = [
        RAW_DATA_DIR,
        PROCESSED_DATA_DIR,
        EVENTS_OUTPUT_DIR,
        OBSERVATIONS_OUTPUT_DIR,
        ISSUES_OUTPUT_DIR,
        CLUSTERS_OUTPUT_DIR,
        REPORTS_OUTPUT_DIR,
        LOGS_OUTPUT_DIR,
    ]
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
