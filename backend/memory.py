import os
import requests
import datetime
import logging
import json
from pathlib import Path
import re

# Setup logging
logger = logging.getLogger(__name__)

# In-memory database (persisted to JSON for across restarts)
MEMORY_DB_FILE = Path(__file__).parent / "memory_db.json"


def normalize_error(error: str) -> str:
    """Normalize error text for matching (exact + signature)."""
    if not isinstance(error, str):
        return ""
    return " ".join(error.lower().strip().split())


def error_signature(error_log: str, category: str = "unknown") -> dict:
    """
    Build a generalized signature for "same pattern" matching.

    Returns dict:
      - signature: stable key for grouping similar incidents
      - extracted: optional details (e.g. module name)
    """
    text = normalize_error(error_log)

    # Missing dependency / import patterns
    m = re.search(r"(modulenotfounderror|importerror):\s*no module named ['\"]?([a-z0-9_.-]+)['\"]?", text)
    if m:
        return {
            "signature": "import:no-module-named",
            "extracted": {"module": m.group(2)},
        }

    # SQLite missing table pattern
    if "sqlite3.operationalerror" in text and "no such table" in text:
        return {"signature": "sqlite:no-such-table", "extracted": {}}

    # Postgres auth failure pattern
    if "password authentication failed" in text:
        return {"signature": "db:password-auth-failed", "extracted": {}}

    # Fallback: category + first line only, with numbers collapsed
    first_line = text.split("\\n", 1)[0]
    first_line = re.sub(r"\\b\\d+\\b", "<n>", first_line)
    return {"signature": f"{category}:{first_line[:160]}", "extracted": {}}


class LocalMemory:
    """Simple in-memory exact-match database for incidents."""
    
    def __init__(self):
        self.db = []
        self.load_from_disk()
    
    def load_from_disk(self):
        """Load memory from JSON file if it exists."""
        if MEMORY_DB_FILE.exists():
            try:
                with open(MEMORY_DB_FILE, 'r') as f:
                    self.db = json.load(f)
                logger.info(f"[LOCAL MEMORY] Loaded {len(self.db)} incidents from disk")
            except Exception as e:
                logger.error(f"[LOCAL MEMORY] Failed to load from disk: {e}")
                self.db = []
        else:
            logger.info("[LOCAL MEMORY] No saved memory found, starting fresh")
    
    def save_to_disk(self):
        """Persist memory to JSON file."""
        try:
            with open(MEMORY_DB_FILE, 'w') as f:
                json.dump(self.db, f, indent=2)
            logger.info(f"[LOCAL MEMORY] Saved {len(self.db)} incidents to disk")
        except Exception as e:
            logger.error(f"[LOCAL MEMORY] Failed to save to disk: {e}")
    
    def find_exact_match(self, error_log: str):
        """Find exact match in local memory.
        
        Returns:
            dict with keys: original, solution, category, count, first_seen, last_seen
            OR None if not found
        """
        normalized = normalize_error(error_log)
        
        for item in self.db:
            if normalize_error(item.get("original", "")) == normalized:
                logger.info(f"[LOCAL MEMORY] ✅ EXACT MATCH FOUND! Seen {item.get('count', 0)}x before")
                return item
        
        logger.info("[LOCAL MEMORY] ❌ No exact match found in local memory")
        return None

    def find_signature_match(self, error_log: str, category: str = "unknown"):
        """Find best match by generalized signature (pattern match)."""
        sig = error_signature(error_log, category=category).get("signature")
        if not sig:
            return None
        best = None
        for item in self.db:
            if item.get("signature") == sig:
                # Prefer higher count / most recent
                if not best:
                    best = item
                else:
                    if int(item.get("count", 1) or 1) > int(best.get("count", 1) or 1):
                        best = item
        return best
    
    def store_incident(self, error_log: str, solution: str, category: str = "unknown") -> dict:
        """Store incident in local memory.
        
        If exact match exists, increment count.
        Otherwise, create new entry.
        """
        normalized = normalize_error(error_log)
        sig_info = error_signature(error_log, category=category)
        signature = sig_info.get("signature")
        extracted = sig_info.get("extracted", {}) or {}
        
        # 1) Exact match
        for item in self.db:
            if normalize_error(item.get("original", "")) == normalized:
                previous_count = int(item.get("count", 1) or 1)
                # Increment count
                item["count"] = previous_count + 1
                item["last_seen"] = datetime.datetime.now().isoformat()
                item["signature"] = item.get("signature") or signature
                item["extracted"] = item.get("extracted") or extracted
                # Update solution if new one is better
                if solution and len(solution) > len(item.get("solution", "")):
                    item["solution"] = solution
                logger.info(f"[LOCAL MEMORY] Incremented count to {item['count']} for existing incident")
                self.save_to_disk()
                return {
                    "seen_before": True,
                    "previous_count": previous_count,
                    "new_count": int(item["count"]),
                    "first_seen": item.get("first_seen"),
                    "last_seen": item.get("last_seen"),
                    "category": item.get("category", category),
                    "signature": item.get("signature") or signature,
                    "extracted": item.get("extracted") or extracted,
                }

        # 2) Signature match (generalized pattern)
        if signature:
            for item in self.db:
                if item.get("signature") == signature:
                    previous_count = int(item.get("count", 1) or 1)
                    item["count"] = previous_count + 1
                    item["last_seen"] = datetime.datetime.now().isoformat()
                    item["category"] = item.get("category") or category
                    # Keep the most informative solution we have
                    if solution and len(solution) > len(item.get("solution", "")):
                        item["solution"] = solution
                    # Track last seen example + extracted fields (module/table/etc.)
                    item["original"] = error_log
                    item["normalized"] = normalized
                    item["extracted"] = extracted or item.get("extracted") or {}
                    logger.info(f"[LOCAL MEMORY] Signature match incremented count to {item['count']} for pattern={signature}")
                    self.save_to_disk()
                    return {
                        "seen_before": True,
                        "previous_count": previous_count,
                        "new_count": int(item["count"]),
                        "first_seen": item.get("first_seen"),
                        "last_seen": item.get("last_seen"),
                        "category": item.get("category", category),
                        "signature": signature,
                        "extracted": extracted,
                    }
        
        # New incident - add to DB
        new_incident = {
            "original": error_log,
            "normalized": normalized,
            "solution": solution,
            "category": category,
            "signature": signature,
            "extracted": extracted,
            "count": 1,
            "first_seen": datetime.datetime.now().isoformat(),
            "last_seen": datetime.datetime.now().isoformat(),
        }
        self.db.append(new_incident)
        logger.info(f"[LOCAL MEMORY] Stored new incident. Total incidents: {len(self.db)}")
        self.save_to_disk()
        return {
            "seen_before": False,
            "previous_count": 0,
            "new_count": 1,
            "first_seen": new_incident.get("first_seen"),
            "last_seen": new_incident.get("last_seen"),
            "category": category,
        }


class HindsightMemory:
    """Interface to Hindsight cloud memory service."""
    
    def __init__(self):
        self.bank_id = os.getenv("HINDSIGHT_BANK_ID", "content-agent")
        self.api_key = os.getenv("HINDSIGHT_API_KEY")
        self.org_path = os.getenv("HINDSIGHT_ORG_PATH", "default")
        self.base_url = os.getenv("HINDSIGHT_BASE_URL", "https://api.vectorize.io")
        self.timeout = 15

    def _memory_base(self) -> str:
        return f"{self.base_url}/v1/{self.org_path}/banks/{self.bank_id}/memories"

    def _extract_logged_error(self, text: str) -> str:
        """Extract stored error from retained content payload."""
        if not isinstance(text, str):
            return ""

        marker = "Error Log:"
        sol_marker = "\nSolution Fix:"

        if marker not in text:
            return ""

        start = text.find(marker) + len(marker)
        end = text.find(sol_marker, start)
        if end == -1:
            end = len(text)

        return text[start:end].strip()

    def _extract_category(self, text: str) -> str:
        """Extract error category from retained content."""
        if not isinstance(text, str):
            return "unknown"
        
        marker = "Category:"
        error_marker = "\nError Log:"
        
        if marker not in text:
            return "unknown"
        
        start = text.find(marker) + len(marker)
        end = text.find(error_marker, start)
        if end == -1:
            end = len(text)
        
        return text[start:end].strip().lower()

    def _extract_solution(self, text: str) -> str:
        """Extract stored solution from retained content payload."""
        if not isinstance(text, str):
            return ""

        marker = "Solution Fix:"
        if marker not in text:
            return text.strip()

        start = text.find(marker) + len(marker)
        return text[start:].strip()

    def retain(self, error_log: str, solution: str, error_category: str = "unknown"):
        """Store error and solution in Hindsight memory."""
        if not self.api_key:
            logger.warning("[HINDSIGHT RETAIN] API key not set")
            return

        url = self._memory_base()
        content = f"Category: {error_category}\nError Log: {error_log}\nSolution Fix: {solution}"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {"items": [{"content": content}]}

        try:
            logger.info(f"[HINDSIGHT RETAIN] Storing: category={error_category}, error_len={len(error_log)}")
            response = requests.post(url, json=payload, headers=headers, timeout=self.timeout)
            if response.status_code >= 400:
                logger.error(f"[HINDSIGHT RETAIN] FAILED {response.status_code}")
            else:
                logger.info(f"[HINDSIGHT RETAIN] ✅ SUCCESS")
        except Exception as e:
            logger.error(f"[HINDSIGHT RETAIN] Error: {type(e).__name__}: {e}")

    def recall(self, error_log: str, threshold: float = 0.3):
        """Recall from Hindsight cloud (used as fallback if no local exact match)."""
        if not self.api_key:
            logger.warning("[HINDSIGHT RECALL] API key not set")
            return None

        url = f"{self._memory_base()}/recall"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {"query": error_log}

        try:
            logger.info(f"[HINDSIGHT RECALL] Querying cloud...")
            response = requests.post(url, json=payload, headers=headers, timeout=self.timeout)
            logger.info(f"[HINDSIGHT RECALL] Response: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                results = data.get("results", [])
                
                if not results:
                    logger.info("[HINDSIGHT RECALL] No cloud results")
                    return None
                
                logger.info(f"[HINDSIGHT RECALL] Found {len(results)} cloud matches")
                best_match = results[0]
                best_score = best_match.get("score", 0.0)
                best_text = best_match.get("text", "")
                
                matched_error = self._extract_logged_error(best_text)
                matched_solution = self._extract_solution(best_text)
                matched_category = self._extract_category(best_text)
                repeat_count = len(results)
                confidence_score = round(best_score * 100, 1)
                
                logger.info(f"[HINDSIGHT RECALL] Best match: {confidence_score}% similarity, {repeat_count}x results, category={matched_category}")
                
                return {
                    "error_log": matched_error or error_log,
                    "solution": matched_solution or "Solution found in memory.",
                    "timestamp": datetime.datetime.now().isoformat(),
                    "confidence": confidence_score,
                    "seen_before_count": repeat_count,
                    "error_category": matched_category,
                    "is_repeated": repeat_count >= 2,
                    "raw_similarity_score": round(best_score, 3),
                    "hindsight_found_it": True,
                }
            else:
                logger.error(f"[HINDSIGHT RECALL] API error {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"[HINDSIGHT RECALL] Error: {type(e).__name__}: {e}")
            return None


# Global instances
local_memory = LocalMemory()
hindsight_memory = HindsightMemory()
