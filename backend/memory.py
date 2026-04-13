import os
import requests
import datetime


class HindsightMemory:
    def __init__(self):
        # Allow Hindsight configuration via .env
        self.bank_id = os.getenv("HINDSIGHT_BANK_ID", "content-agent")
        self.api_key = os.getenv("HINDSIGHT_API_KEY")
        self.org_path = os.getenv("HINDSIGHT_ORG_PATH", "default")
        self.base_url = os.getenv("HINDSIGHT_BASE_URL", "https://api.vectorize.io")

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

    def _normalize_error(self, text: str) -> str:
        return " ".join((text or "").strip().lower().split())

    def _extract_solution(self, text: str) -> str:
        """Extract stored solution from retained content payload."""
        if not isinstance(text, str):
            return ""

        marker = "Solution Fix:"
        if marker not in text:
            return text.strip()

        start = text.find(marker) + len(marker)
        return text[start:].strip()

    def retain(self, error_log: str, solution: str):
        if not self.api_key:
            print("WARNING: HINDSIGHT_API_KEY not set. Cannot retain.")
            return

        url = self._memory_base()
        content = f"Error Log: {error_log}\nSolution Fix: {solution}"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {"items": [{"content": content}]}

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=15)
            if response.status_code >= 400:
                print(f"Hindsight Retain API returned {response.status_code}: {response.text}")
        except Exception as e:
            print(f"Hindsight API Retain Error: {e}")

    def recall(self, error_log: str, threshold: float = 0.3):
        if not self.api_key:
            print("WARNING: HINDSIGHT_API_KEY not set. Cannot recall.")
            return None

        url = f"{self._memory_base()}/recall"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {"query": error_log}

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=15)
            if response.status_code == 200:
                data = response.json()
                results = data.get("results", [])

                if results:
                    best_match = results[0]
                    score = best_match.get("score", 1.0)

                    if score >= threshold:
                        normalized_current = self._normalize_error(error_log)
                        exact_repeats = 0
                        matched_error = self._extract_logged_error(best_match.get("text", ""))
                        matched_solution = self._extract_solution(best_match.get("text", ""))

                        for item in results:
                            raw_text = item.get("text", "")
                            logged_error = self._extract_logged_error(raw_text)
                            normalized_logged = self._normalize_error(logged_error or raw_text)
                            if (
                                normalized_logged == normalized_current
                                or normalized_current in normalized_logged
                            ):
                                exact_repeats += 1

                        return {
                            "error_log": matched_error or error_log,
                            "solution": matched_solution or best_match.get("text", "Content found in memory."),
                            "timestamp": datetime.datetime.now().isoformat(),
                            "confidence": round(score * 100, 2),
                            # Exact repeated incidents that match current error text.
                            "seen_before_count": exact_repeats,
                            # Broader semantic recalls from memory.
                            "similar_matches_count": len(results),
                        }
            else:
                error_text = response.text
                if response.status_code == 401 and "Invalid organization path" in error_text:
                    print(
                        "Hindsight Recall API returned 401: Invalid organization path. "
                        "Set HINDSIGHT_ORG_PATH in .env to your org path from Vectorize Cloud."
                    )
                else:
                    print(f"Hindsight Recall API returned {response.status_code}: {error_text}")
        except Exception as e:
            print(f"Hindsight API Recall Error: {e}")

        return None
