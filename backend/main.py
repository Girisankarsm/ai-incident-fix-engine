import os
import logging
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from groq import Groq

from memory import HindsightMemory
from advanced_features import IncidentAnalyzer, ErrorCategory

load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="AI Incident Fix Engine")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

memory_system = HindsightMemory()
incident_history: list[str] = []
incident_feed: list[dict] = []
analyzer = IncidentAnalyzer()  # Initialize analyzer

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

groq_client = None
if os.getenv("GROQ_API_KEY"):
    groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

class AnalyzeRequest(BaseModel):
    user_id: str
    error_log: str = Field(..., min_length=1, description="The error log or stack trace to analyze")

class AnalyzeResponse(BaseModel):
    solution: str
    memory_used: bool
    past_reference: dict | None = None
    seen_before_count: int | None = None
    confidence: float | None = None
    incident_summary: dict
    recent_incidents: list[dict]
    system_status: dict
    # New advanced fields
    error_category: str = "unknown"
    severity: str = "MEDIUM"
    severity_score: int = 5
    root_causes: list[str] = []
    affected_components: list[str] = []
    incident_score: dict = {}
    recommended_actions: list[str] = []
    trend_analysis: dict = {}
    trend_analysis: dict = {}

    trend_analysis: dict = {}



def _normalize_error(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def _local_seen_before_count(error_log: str, threshold: float = 0.5) -> int:
    """
    Count how many previous incidents are at least `threshold` similar to current log.
    This keeps Seen Before accurate even when remote recall payload format varies.
    """
    current = _normalize_error(error_log)
    seen = 0
    for previous in incident_history:
        ratio = SequenceMatcher(None, current, _normalize_error(previous)).ratio()
        if ratio >= threshold:
            seen += 1
    return seen


def _build_fallback_solution(error_log: str, past_memory: dict | None) -> str:
    """Build a more specific fallback solution with actionable steps."""
    if past_memory and past_memory.get("solution"):
        intro = (
            "Based on analysis, a similar incident was found. "
            "The previously successful fix involved:\n\n"
        )
        reference = (
            f"Previous Error: {past_memory['error_log']}\n"
            f"Previous Fix: {past_memory['solution']}\n\n"
        )
        return (
            f"{intro}"
            f"{reference}"
            "Apply the same approach to this incident. "
            "If the error differs slightly, modify the fix steps accordingly.\n\n"
            f"Current Error Context:\n{error_log}"
        )
    else:
        return (
            "No exact match found. Providing best-effort resolution.\n\n"
            "Recommended diagnostic and resolution steps:\n"
            "1. Review the exact error message and stack trace - identify which service/component failed.\n"
            "2. Check recent deployments or configuration changes that might have triggered this.\n"
            "3. Validate all dependencies, services, and environment variables are properly configured.\n"
            "4. Check system resources (disk space, memory, file descriptor limits):\n"
            "   - df -h (disk usage)\n"
            "   - free -m (memory)\n"
            "   - ulimit -a (file descriptor limits)\n"
            "5. Review logs for the affected service:\n"
            "   - tail -100f /var/log/app.log\n"
            "   - journalctl -u service_name -n 50\n"
            "6. If it's a database error:\n"
            "   - Check database connectivity and authentication\n"
            "   - Verify table/schema existence\n"
            "7. If it's a network error:\n"
            "   - Check DNS resolution: nslookup/dig\n"
            "   - Check connectivity: telnet/nc\n"
            "   - Review firewall rules\n"
            "8. Once identified, document the root cause and fix for future reference.\n\n"
            f"Error Details:\n{error_log}"
        )


def _is_invalid_api_key_error(error: Exception) -> bool:
    message = str(error).lower()
    return "invalid api key" in message or "invalid_api_key" in message


def _should_use_memory(
    current_category: str,
    past_memory: dict | None,
    confidence: float,
    seen_count: int
) -> bool:
    """
    Determine if memory should actually be used.
    
    Fixes critical issue: system was using memory even when categories didn't match.
    
    Rules:
    1. Must have a memory match
    2. Categories must match (sqlite != permission)
    3. Confidence must be reasonable (>50%)
    4. Seen count must be > 0
    """
    if not past_memory:
        return False
    
    # Get past memory category
    past_category = past_memory.get("error_category", "unknown")
    
    # Rule 1: Categories must match - THIS IS CRITICAL
    if current_category != past_category:
        logger.warning(
            f"Memory rejected: category mismatch. "
            f"Current: {current_category}, Past: {past_category}"
        )
        return False
    
    # Rule 2: Confidence must be adequate (>50%)
    if confidence < 50:
        logger.warning(
            f"Memory rejected: low confidence {confidence}%. "
            f"Threshold is 50%"
        )
        return False
    
    # Rule 3: Seen count must indicate actual previous occurrence
    if seen_count == 0:
        logger.warning(
            "Memory rejected: seen_before_count is 0. "
            "Cannot use memory for first occurrence"
        )
        return False
    
    logger.info(
        f"Memory validated: category={current_category}, "
        f"confidence={confidence}%, seen={seen_count}"
    )
    return True


def _record_incident(
    error_log: str, 
    memory_used: bool, 
    confidence: float, 
    seen_count: int,
    category: str,
    severity: str,
    severity_score: int,
    past_memory: dict | None = None
) -> None:
    """Record incident in feed, keeping only the most recent 15."""
    incident_feed.insert(0, {
        "error_log": error_log,
        "memory_used": memory_used,
        "confidence": confidence,
        "seen_before_count": seen_count,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "error_category": category,
        "severity": severity,
        "severity_score": severity_score,
        # Store category in memory for future validation
        "past_memory": past_memory
    })
    # Keep only the 15 most recent incidents
    incident_feed[:] = incident_feed[:15]


@app.get("/api/health")
def health_check():
    return {
        "status": "ok",
        "groq_configured": bool(groq_client),
        "hindsight_configured": bool(os.getenv("HINDSIGHT_API_KEY")),
        "recent_incident_count": len(incident_feed),
    }


@app.get("/api/incidents")
def recent_incidents():
    return {
        "incidents": incident_feed,
    }

@app.post("/api/analyze", response_model=AnalyzeResponse)
def analyze_error(request: AnalyzeRequest):
    """Analyze an incident using Hindsight memory and Groq AI with advanced features."""
    error_log = request.error_log.strip()
    
    if not error_log:
        raise HTTPException(status_code=400, detail="Error log cannot be empty")
    
    logger.info(f"Analyzing incident for user {request.user_id}")
    
    # ADVANCED: Classify and analyze the error
    error_category = analyzer.classify_error(error_log)
    severity_info = analyzer.assess_severity(error_log, error_category)
    root_causes = analyzer.extract_root_causes(error_log, error_category)
    affected_components = analyzer.get_affected_components(error_log)
    
    logger.info(f"Error classified as: {error_category.value}, Severity: {severity_info['severity']}")
    
    # 1. Recall Hindsight Memory
    past_memory = memory_system.recall(error_log)
    local_seen_count = _local_seen_before_count(error_log, threshold=0.5)
    
    # CRITICAL FIX: Use proper category-based validation
    memory_used = False
    past_reference_data = None
    seen_count = local_seen_count
    confidence = 0.0
    resolution_mode = "fresh_analysis"

    if past_memory:
        # Get confidence from memory
        confidence = past_memory.get("confidence", 0.0)
        
        # FIXED: Check if memory should actually be used based on categories
        if _should_use_memory(
            current_category=error_category.value,
            past_memory=past_memory,
            confidence=confidence,
            seen_count=seen_count
        ):
            memory_used = True
            resolution_mode = "memory_guided"
            past_reference_data = {
                "error_log": past_memory["error_log"],
                "solution": past_memory["solution"],
                "timestamp": past_memory["timestamp"]
            }
            logger.info(
                f"Memory VALIDATED and used: category={error_category.value}, "
                f"confidence={confidence}%, seen={seen_count}"
            )
        else:
            # Memory found but not suitable
            memory_used = False
            confidence = 0.0
            seen_count = 0
            resolution_mode = "fresh_analysis"
            logger.info(
                f"Memory REJECTED (category mismatch or low quality): "
                f"past_category={past_memory.get('error_category', 'unknown')}, "
                f"current_category={error_category.value}"
            )

    # Build prompt based on resolution mode
    if memory_used and resolution_mode == "memory_guided":
        prompt = f"""You are a senior DevOps / Full-stack engineer diagnosing issues.
The user encountered the following current error:
---
{error_log}
---

A similar past incident was found:
Past Error: {past_memory['error_log']}
Past Solution: {past_memory['solution']}

Since a similar issue exists with {confidence}% confidence, you MUST start your response exactly with:
"This looks similar to a previous issue we resolved successfully..."

Then, suggest the previously successful fix first. If the fix needs adjustment for current context, provide updated steps.
Provide actionable, specific commands and configurations, not generic advice."""
    else:
        prompt = f"""You are a senior DevOps / Full-stack engineer diagnosing issues.
The user encountered the following current error:
---
{error_log}
---

No matching previous incident found in memory. Provide a fresh analysis and solution.
Be specific with:
- Root cause analysis
- Actionable steps with actual commands/configurations
- File paths and permission specifications
- Not generic advice

For a {error_category.value} error with {severity_info['severity']} severity, provide exact fixes."""
        logger.info("Fresh analysis - generating new incident response without memory")

    groq_status = "fallback"

    try:
        if groq_client:
            try:
                response = groq_client.chat.completions.create(
                    messages=[{"role": "user", "content": prompt}],
                    model="llama-3.3-70b-versatile",
                    temperature=0.2
                )
                solution = response.choices[0].message.content
                groq_status = "ready"
                logger.info("Successfully generated solution with Groq")
            except Exception as groq_error:
                if _is_invalid_api_key_error(groq_error):
                    logger.warning("Invalid Groq API key, using fallback solution")
                    solution = _build_fallback_solution(error_log, past_memory if memory_used else None)
                    groq_status = "invalid-key"
                else:
                    logger.error(f"Groq API error: {groq_error}")
                    raise
        else:
            logger.info("Groq client not configured, using fallback solution")
            solution = _build_fallback_solution(error_log, past_memory if memory_used else None)

        # 2. Retain incident in Hindsight memory with category info
        memory_system.retain(error_log, solution, error_category=error_category.value)
        incident_history.append(error_log)
        _record_incident(
            error_log, 
            memory_used, 
            confidence, 
            seen_count,
            error_category.value,
            severity_info["severity"],
            severity_info["severity_score"],
            past_memory=past_memory
        )
        
        # ADVANCED: Calculate scores and get recommendations
        incident_score = analyzer.calculate_incident_score(
            severity_info["severity_score"],
            confidence / 100.0 if confidence > 0 else 0.5
        )
        recommended_actions = analyzer.get_recommended_actions(
            error_category,
            severity_info["severity"],
            root_causes
        )
        
        # Get trend analysis from the updated incident feed
        trend_analysis = analyzer.analyze_incident_trends(incident_feed)

        return AnalyzeResponse(
            solution=solution,
            memory_used=memory_used,
            past_reference=past_reference_data if memory_used else None,
            seen_before_count=seen_count if memory_used else None,
            confidence=confidence if memory_used else None,
            # New advanced fields
            error_category=error_category.value,
            severity=severity_info["severity"],
            severity_score=severity_info["severity_score"],
            root_causes=root_causes,
            affected_components=affected_components,
            incident_score=incident_score,
            recommended_actions=recommended_actions,
            trend_analysis=trend_analysis,
            incident_summary={
                "status": "known-incident" if memory_used else "new-incident",
                "memory_hits": seen_count if memory_used else 0,
                "similarity_band": (
                    "high" if confidence >= 80 else
                    "medium" if confidence >= 55 else
                    "low"
                ) if memory_used else "new",
            },
            recent_incidents=incident_feed,
            system_status={
                "groq_configured": bool(groq_client),
                "groq_status": groq_status,
                "hindsight_configured": bool(os.getenv("HINDSIGHT_API_KEY")),
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error analyzing incident: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/analyze", response_model=AnalyzeResponse, include_in_schema=False)
def analyze_error_legacy(request: AnalyzeRequest):
    return analyze_error(request)


@app.get("/")
def serve_frontend():
    return FileResponse(FRONTEND_DIR / "index.html")


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")