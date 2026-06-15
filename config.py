"""Global configuration settings for the Organizational Event Intelligence Pipeline.

This module acts as the single source of truth for all application configuration,
including paths, local model hosts, parameter thresholds, and logging settings.
"""

from pathlib import Path

# =====================================================================
# SECTION 1: PROJECT PATHS
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
REPORTS_OUTPUT_DIR = OUTPUTS_DIR / "reports"
LOGS_OUTPUT_DIR = OUTPUTS_DIR / "logs"

# =====================================================================
# SECTION 2: OLLAMA CONFIGURATION
# =====================================================================

OLLAMA_HOST: str = "http://localhost:11434"
OLLAMA_MODEL: str = "llama3.1:8b-instruct"
OLLAMA_TIMEOUT_SECONDS: int = 120

# =====================================================================
# SECTION 3: EVENT EXTRACTION SETTINGS
# =====================================================================

MIN_EVENT_CONFIDENCE: float = 0.70
MAX_EVENTS_PER_BATCH: int = 50

# =====================================================================
# SECTION 4: ISSUE TRACKING SETTINGS
# =====================================================================

ISSUE_MATCH_THRESHOLD: float = 0.85

# =====================================================================
# SECTION 5: REPORT GENERATION SETTINGS
# =====================================================================

MAX_CRITICAL_ISSUES: int = 10
MAX_EXECUTIVE_FINDINGS: int = 5

# =====================================================================
# SECTION 6: LOGGING SETTINGS
# =====================================================================

LOG_LEVEL: str = "INFO"


# =====================================================================
# SECTION 7: FILE CREATION HELPER
# =====================================================================

def create_required_directories() -> None:
    """Create all required project directories if they do not exist."""
    directories = [
        RAW_DATA_DIR,
        PROCESSED_DATA_DIR,
        EVENTS_OUTPUT_DIR,
        REPORTS_OUTPUT_DIR,
        LOGS_OUTPUT_DIR,
    ]
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
