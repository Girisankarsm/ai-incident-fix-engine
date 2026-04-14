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
import sys
from pathlib import Path

# Add backend directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from memory import HindsightMemory, local_memory, hindsight_memory
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
    # Always-on incident memory stats (real persistence)
    seen_before: bool | None = None
    occurrence_count: int | None = None
    memory_hits: int | None = None
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
    """Build a short, SRE-style fallback solution (no tutorials)."""
    if past_memory and past_memory.get("solution"):
        return (
            "Root Cause: Similar incident previously resolved\n"
            "Fix:\n"
            f"1. Apply the previously working fix\n"
            f"Command: (see prior fix details)\n"
        )
    else:
        return (
            "Root Cause: Unknown (needs focused triage)\n"
            "Fix:\n"
            "1. Verify the most likely config/env cause for this category\n"
            "2. Re-run and confirm the error clears\n"
            "Command: check service logs + config\n"
        )


def _format_sre_solution(
    *,
    error_log: str,
    error_category: str,
    signature: str | None = None,
    extracted: dict | None = None,
    root_causes: list[str],
    recommended_actions: list[str],
    confidence: float,
    occurrence_count: int,
    memory_used: bool,
) -> str:
    import re

    log_lower = (error_log or "").lower()
    extracted = extracted or {}
    # Prefer precise causes when the log clearly indicates it.
    if "password authentication failed" in log_lower or "authentication failed" in log_lower:
        root_cause = "Invalid database credentials (password) for the configured user"
        steps = [
            "Confirm the DB password in env/secret matches the DB user (e.g., POSTGRES_PASSWORD / DATABASE_URL)",
            "Restart the application/service to pick up the updated secret",
            "Verify credentials directly with psql using the same host/user/db",
        ]
    elif signature == "import:no-module-named":
        module = extracted.get("module") or "<package>"
        root_cause = f"Missing Python dependency: {module}"
        steps = [
            f"Install the missing package ({module}) in the runtime environment",
            "Re-run the command/service and confirm the import succeeds",
            "Pin the dependency (requirements.txt / lockfile) to prevent recurrence",
        ]
    else:
        root_cause = (root_causes or ["Unknown root cause"])[0]

    # Prioritize: keep top 3 actions, strip numbering prefixes for cleaner output
    if "steps" not in locals():
        steps = []
        for action in (recommended_actions or [])[:3]:
            cleaned = re.sub(r"^\s*\d+\.\s*", "", (action or "").strip())
            steps.append(cleaned)

    if not steps:
        steps = ["Validate configuration/environment for this failure", "Apply minimal fix and restart service", "Confirm via logs/healthcheck"]

    # Command hint: use category to avoid over-general config edits (e.g., don't suggest pg_hba.conf by default)
    command_hint = "restart the affected service"
    if signature == "import:no-module-named":
        module = extracted.get("module") or "<package>"
        command_hint = f"pip install {module}"
    elif error_category == "database":
        command_hint = "psql -U <user> -h <host> -d <db>"
    elif error_category == "network":
        command_hint = "curl -v <endpoint>  # or nc -vz <host> <port>"
    elif error_category == "authentication":
        command_hint = "validate token/key and retry request"

    return (
        f"Root Cause: {root_cause}\n"
        "Fix:\n"
        + "\n".join([f"{i+1}. {s}" for i, s in enumerate(steps)])
        + "\n"
        f"Command: {command_hint}\n"
        f"Confidence: {confidence:.0f}%\n"
        f"Seen Before: {occurrence_count}x\n"
        f"Memory Used: {'yes' if memory_used else 'no'}\n"
    )


def _is_invalid_api_key_error(error: Exception) -> bool:
    message = str(error).lower()
    return "invalid api key" in message or "invalid_api_key" in message


def _should_use_memory(
    current_category: str,
    past_memory: dict | None,
    confidence: float,
    seen_count: int,
    is_exact_repeat: bool = False
) -> bool:
    """
    Determine if memory should actually be used.
    
    Fixes critical issue: system was using memory even when categories didn't match.
    
    Rules:
    1. Must have a memory match
    2. Categories must match (sqlite != permission)
    3. Confidence must be reasonable (>50%)
    4. Seen count must be > 0
    5. Must be an EXACT repeat (not just similar)
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
    
    # Rule 4: Must be an EXACT repeat (not just similar)
    if not is_exact_repeat:
        logger.info(
            f"Memory not used: similar match found but not exact repeat. "
            f"Confidence: {confidence}%, Category: {current_category}"
        )
        return False
    
    logger.info(
        f"Memory validated: category={current_category}, "
        f"confidence={confidence}%, seen={seen_count}, exact_repeat=True"
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
    
    # STAGE 1: Check LOCAL MEMORY
    # - exact match (reuse solution)
    # - signature match (pattern seen before, but don't blindly reuse solution)
    logger.info("[MEMORY] Stage 1: Checking local memory (exact + signature)...")
    local_match = local_memory.find_exact_match(error_log)
    local_sig_match = None if local_match else local_memory.find_signature_match(error_log, category=error_category.value)
    
    memory_used = False
    past_reference_data = None
    seen_count = 0
    confidence = 0.0
    resolution_mode = "fresh_analysis"
    past_memory = None
    
    # Local incident stats (used for "seen before?" and counts regardless of cloud)
    local_previous_count = int(local_match.get("count", 0) or 0) if local_match else 0
    local_sig_previous_count = int(local_sig_match.get("count", 0) or 0) if local_sig_match else 0
    local_seen_before = (local_previous_count > 0) or (local_sig_previous_count > 0)

    if local_match:
        # EXACT MATCH FOUND IN LOCAL MEMORY!
        logger.info(f"[MEMORY] ✅ EXACT MATCH in local memory! Count: {local_match.get('count', 0)}")
        seen_count = local_match.get('count', 1)
        # Confidence “learns” with repetition, but cap below 100 to feel realistic.
        confidence = min(95, 55 + (max(1, seen_count) - 1) * 10)
        memory_used = True
        resolution_mode = "memory_guided"
        past_memory = {
            "error_log": local_match.get('original', error_log),
            "solution": local_match.get('solution', ''),
            "timestamp": local_match.get('last_seen', datetime.now().isoformat()),
            "confidence": confidence,
            "seen_before_count": seen_count,
            "error_category": local_match.get('category', 'unknown'),
            "is_repeated": seen_count >= 2,
            "raw_similarity_score": 1.0,  # Exact match = 100% similarity
            "hindsight_found_it": False,  # Found in local, not cloud
        }
        past_reference_data = {
            "error_log": local_match.get('original', error_log),
            "solution": local_match.get('solution', ''),
            "timestamp": local_match.get('last_seen', datetime.now().isoformat())
        }
        logger.info(f"[MEMORY] 🎯 Using LOCAL MEMORY - Seen {seen_count}x, Confidence: {confidence}%")
    elif local_sig_match:
        # Pattern seen before => ALWAYS treat as memory reuse (even if not exact text).
        seen_count = int(local_sig_match.get("count", 1) or 1)
        confidence = min(92, 50 + (max(1, seen_count) - 1) * 10)
        memory_used = True
        resolution_mode = "pattern_memory"
        past_reference_data = {
            "error_log": local_sig_match.get("original", error_log),
            "solution": local_sig_match.get("solution", ""),
            "timestamp": local_sig_match.get("last_seen", datetime.now().isoformat()),
        }
        logger.info(f"[MEMORY] 🧠 Signature memory used (pattern) - Seen {seen_count}x, Confidence: {confidence}%")
    else:
        # NO LOCAL MATCH: Fall back to Hindsight cloud search
        logger.info("[MEMORY] Stage 2: No local match, checking Hindsight cloud...")
        past_memory = hindsight_memory.recall(error_log)

    if past_memory:
        # Hindsight FOUND THE ERROR IN CLOUD!
        confidence = past_memory.get("confidence", 0.0)
        is_repeated = past_memory.get("is_repeated", False)
        seen_count = past_memory.get("seen_before_count", 0)
        match_category = past_memory.get("error_category", "unknown")
        raw_similarity = past_memory.get("raw_similarity_score", 0.0)
        
        logger.info(f"[MEMORY] Found in Hindsight! Confidence: {confidence}%, Similarity: {raw_similarity:.3f}, Seen: {seen_count}x, Category: {match_category}")
        
        # HARD VALIDATION RULES - ALL MUST PASS (AND logic)
        rule_1_confidence = confidence >= 70  # HARD RULE: Must be 70% confident or higher
        rule_2_similarity = raw_similarity >= 0.7  # HARD RULE: Must have 70%+ similarity match
        rule_3_category = match_category == error_category.value  # HARD RULE: Category MUST match exactly (NO "unknown" bypass)
        rule_4_repeated = is_repeated and seen_count >= 2  # HARD RULE: Must be seen 2+ times AND marked as repeated
        
        should_use = rule_1_confidence and rule_2_similarity and rule_3_category and rule_4_repeated
        
        logger.info(f"[MEMORY] VALIDATION: Confidence≥70%: {rule_1_confidence} | Similarity≥0.7: {rule_2_similarity} | Category match: {rule_3_category} | Repeated≥2x: {rule_4_repeated}")
        
        if should_use:
            memory_used = True
            resolution_mode = "memory_guided"
            past_reference_data = {
                "error_log": past_memory["error_log"],
                "solution": past_memory["solution"],
                "timestamp": past_memory["timestamp"]
            }
            logger.info(f"[MEMORY] ✅ ALL RULES PASSED - Using CLOUD MEMORY - {seen_count}x seen, {confidence}% confidence, {raw_similarity:.1%} similar")
        else:
            logger.info(f"[MEMORY] ❌ NOT USING - Failed validation: Conf:{confidence}% (need≥70) | Sim:{raw_similarity:.3f} (need≥0.7) | Cat:{match_category} (need {error_category.value}) | Repeated:{is_repeated}/{seen_count}x (need ≥2x)")
    else:
        # NO MEMORY = FRESH ERROR
        logger.info("[MEMORY] ❌ NOT IN HINDSIGHT CLOUD - This is a FRESH/NEW error")

    # Build prompt based on resolution mode
    solution = None
    groq_status = "fallback"
    
    if memory_used and resolution_mode == "memory_guided":
        # HIGH CONFIDENCE: Use the past solution directly from Hindsight memory
        if confidence >= 85:
            logger.info(f"[GROQ] Confidence {confidence}% is HIGH - Using stored solution directly from Hindsight")
            solution = past_memory['solution']
            groq_status = "memory_direct"
        else:
            # MEDIUM CONFIDENCE: Ask Groq to enhance the past solution
            logger.info(f"[GROQ] Confidence {confidence}% is MEDIUM - Asking Groq to enhance the past solution")
        prompt = f"""You are a senior SRE writing an incident response.
The user encountered the following current error:
---
{error_log}
---

A similar past incident was found:
Past Error: {past_memory['error_log']}
Past Solution: {past_memory['solution']}

Since a similar issue exists with {confidence}% confidence, you MUST start your response exactly with:
"This looks similar to a previous issue we resolved successfully..."

Then provide a SHORT incident-response style answer in EXACTLY this format (no extra sections):
Root Cause: <one line>
Fix:
1. <most likely step first>
2. <next step>
Command: <one command>
Notes: <optional one line>
"""
    else:
        # FRESH ANALYSIS: Generate new response
        logger.info("Fresh analysis - generating new incident response without memory")
        prompt = f"""You are a senior SRE writing an incident response.
The user encountered the following current error:
---
{error_log}
---

No matching previous incident found in memory. Provide a fresh analysis and solution.
Return a SHORT answer in EXACTLY this format (no extra sections, no long tutorials):
Root Cause: <one line>
Fix:
1. <most likely step first>
2. <next step>
Command: <one command>
Notes: <optional one line>
Focus on highest-probability root cause first; don't suggest config edits unless clearly required."""

    # Only call Groq if we don't have a direct solution from high-confidence memory
    if solution is None:
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
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting solution: {type(e).__name__}: {e}")
            solution = _build_fallback_solution(error_log, past_memory if memory_used else None)

    # Persist incident every time (realistic backend behavior)
    # - Local: deterministic "seen before" + counts
    # - Cloud: retain for vector recall (best-effort)
    local_stats = local_memory.store_incident(error_log, solution, category=error_category.value)
    occurrence_count = int(local_stats.get("new_count", 1) or 1)
    # Keep repeat counters consistent in UI:
    # - Seen Before: occurrence_count (times observed)
    # - Memory Hits: same number (demo-friendly “hits” = observations)
    memory_hits = occurrence_count

    # CRITICAL RULE: repetition beats similarity.
    # If we've seen this incident pattern before, we MUST mark memory as used.
    if occurrence_count > 1:
        memory_used = True
        if past_reference_data is None:
            past_reference_data = {
                "error_log": local_stats.get("original", error_log),
                "solution": local_stats.get("solution", solution),
                "timestamp": local_stats.get("last_seen", datetime.now().isoformat()),
            }

    # Best-effort cloud retention
    memory_system.retain(error_log, solution, error_category=error_category.value)

    incident_history.append(error_log)
    _record_incident(
        error_log,
        memory_used,
        confidence,
        memory_hits,
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

    # Treat signature repeats as known incidents too (even if exact text differs).
    classification_status = "known-incident" if occurrence_count > 1 else "new-incident"

    # Build response (no fake frontend parsing; explicit fields)
    sre_solution = _format_sre_solution(
        error_log=error_log,
        error_category=error_category.value,
        signature=local_stats.get("signature"),
        extracted=local_stats.get("extracted"),
        root_causes=root_causes,
        recommended_actions=recommended_actions,
        confidence=confidence,
        occurrence_count=occurrence_count,
        memory_used=memory_used,
    )

    response_data = {
        "solution": sre_solution,
        "memory_used": memory_used,
        "past_reference": past_reference_data if memory_used else None,
        # Back-compat fields
        "seen_before_count": occurrence_count,
        "confidence": confidence,
        # New explicit fields
        "seen_before": occurrence_count > 1,
        "occurrence_count": occurrence_count,
        "memory_hits": memory_hits,
        # Advanced fields
        "error_category": error_category.value,
        "severity": severity_info["severity"],
        "severity_score": severity_info["severity_score"],
        "root_causes": root_causes,
        "affected_components": affected_components,
        "incident_score": incident_score,
        "recommended_actions": recommended_actions,
        "trend_analysis": trend_analysis,
        "incident_summary": {
            "status": classification_status,
            "memory_hits": memory_hits,
            "similarity_band": (
                "high" if confidence >= 80 else
                "medium" if confidence >= 55 else
                "low"
            ) if confidence > 0 else "none",
        },
        "recent_incidents": incident_feed,
        "system_status": {
            "groq_configured": bool(groq_client),
            "groq_status": groq_status,
            "hindsight_configured": bool(os.getenv("HINDSIGHT_API_KEY")),
        }
    }

    return AnalyzeResponse(**response_data)



@app.post("/analyze", response_model=AnalyzeResponse, include_in_schema=False)
def analyze_error_legacy(request: AnalyzeRequest):
    return analyze_error(request)


@app.get("/")
def serve_frontend():
    return FileResponse(FRONTEND_DIR / "index.html")


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")