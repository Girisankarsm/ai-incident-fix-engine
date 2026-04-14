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
    intro = (
        "This looks similar to a previous issue...\n\n"
        if past_memory else
        "No identical memory was found yet, so here is a first-pass incident response plan.\n\n"
    )
    reference = ""
    if past_memory:
        reference = (
            f"Previous incident: {past_memory['error_log']}\n"
            f"Previous fix: {past_memory['solution']}\n\n"
        )

    return (
        f"{intro}"
        f"{reference}"
        "Recommended next steps:\n"
        "1. Identify the failing service, dependency, or migration named in the error.\n"
        "2. Check the most recent deploy, config change, or schema change touching that component.\n"
        "3. Validate environment variables, credentials, and network access before retrying.\n"
        "4. Reproduce the issue locally or in staging with the same input if possible.\n"
        "5. Capture the confirmed root cause and final fix so similar incidents can be resolved faster next time.\n\n"
        f"Current error:\n{error_log}"
    )


def _is_invalid_api_key_error(error: Exception) -> bool:
    message = str(error).lower()
    return "invalid api key" in message or "invalid_api_key" in message


def _record_incident(
    error_log: str, 
    memory_used: bool, 
    confidence: float, 
    seen_count: int,
    category: str,
    severity: str,
    severity_score: int
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
    
    memory_used = False
    past_reference_data = None
    seen_count = 0
    confidence = 0.0

    if past_memory:
        memory_used = True
        past_reference_data = {
            "error_log": past_memory["error_log"],
            "solution": past_memory["solution"],
            "timestamp": past_memory["timestamp"]
        }
        seen_count = max(past_memory.get("seen_before_count", 0), local_seen_count)
        confidence = past_memory.get("confidence", 0.0)
        logger.info(f"Memory hit found with confidence {confidence}%")

        prompt = f"""You are a senior DevOps / Full-stack engineer diagnosing issues.
The user encountered the following current error:
---
{error_log}
---

Hindsight Memory has found a similar past incident:
Past Error: {past_memory['error_log']}
Past Solution: {past_memory['solution']}

Since a similar issue exists, you MUST start your response exactly with "This looks similar to a previous issue...".
Then, suggest the previously successful fix first. If the fix is not fully applicable, provide any updated or modified steps.
"""
    else:
        prompt = f"""You are a senior DevOps / Full-stack engineer diagnosing issues.
The user encountered the following current error:
---
{error_log}
---

There is no similar past issue in Hindsight Memory. 
Please provide a general solution and step-by-step fix for this error.
"""
        logger.info("No memory hit found - generating new incident response")

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
                    solution = _build_fallback_solution(error_log, past_memory)
                    groq_status = "invalid-key"
                else:
                    logger.error(f"Groq API error: {groq_error}")
                    raise
        else:
            logger.info("Groq client not configured, using fallback solution")
            solution = _build_fallback_solution(error_log, past_memory)

        # 2. Retain incident in Hindsight memory
        memory_system.retain(error_log, solution)
        incident_history.append(error_log)
        _record_incident(
            error_log, 
            memory_used, 
            confidence, 
            seen_count,
            error_category.value,
            severity_info["severity"],
            severity_info["severity_score"]
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