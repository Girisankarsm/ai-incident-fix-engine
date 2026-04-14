"""
Advanced features module for incident analysis.
Implements error classification, severity assessment, and root cause analysis.
"""

from enum import Enum
from typing import Optional, List, Dict, Any
import re
from datetime import datetime, timedelta


class ErrorCategory(str, Enum):
    """Enum for error categories."""
    DATABASE = "database"
    NETWORK = "network"
    IMPORT = "import"
    AUTHENTICATION = "authentication"
    RESOURCE = "resource"
    API = "api"
    PERMISSION = "permission"
    UNKNOWN = "unknown"


class SeverityLevel(str, Enum):
    """Enum for severity levels."""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


# Error classification patterns
ERROR_PATTERNS = {
    ErrorCategory.DATABASE: {
        "keywords": [
            "sqlite", "postgres", "mysql", "mongodb", "oracle",
            "connection pool", "table", "transaction", "database",
            "sql error", "query", "constraint", "foreign key"
        ],
        "patterns": [
            r"sqlite\d*\..*Error",
            r"psycopg2\..*",
            r"pymongo\..*",
            r"sqlalchemy\..*"
        ]
    },
    ErrorCategory.NETWORK: {
        "keywords": [
            "timeout", "connection refused", "dns", "unreachable",
            "reset by peer", "broken pipe", "network", "socket",
            "http", "ssl", "certificate", "tls"
        ],
        "patterns": [
            r".*Timeout.*",
            r".*ConnectionError.*",
            r".*SSLError.*",
            r"requests\.exceptions\..*"
        ]
    },
    ErrorCategory.IMPORT: {
        "keywords": [
            "modulenotfound", "importerror", "no module",
            "cannot import", "import", "module"
        ],
        "patterns": [
            r"ModuleNotFoundError.*",
            r"ImportError.*",
            r"No module named.*"
        ]
    },
    ErrorCategory.AUTHENTICATION: {
        "keywords": [
            "unauthorized", "forbidden", "401", "403",
            "authentication", "credentials", "invalid token",
            "expired", "denied", "access denied"
        ],
        "patterns": [
            r".*401.*",
            r".*403.*",
            r".*Unauthorized.*",
            r".*Forbidden.*"
        ]
    },
    ErrorCategory.RESOURCE: {
        "keywords": [
            "memory", "memoryerror", "too many", "limit reached",
            "descriptor", "disk", "cpu", "out of"
        ],
        "patterns": [
            r"MemoryError.*",
            r".*too many.*",
            r".*limit.*",
            r"OSError.*24.*"  # Too many open files
        ]
    },
    ErrorCategory.API: {
        "keywords": [
            "429", "500", "502", "503", "httperror",
            "status code", "bad gateway", "service unavailable"
        ],
        "patterns": [
            r".*[45]\d{2}.*",
            r"HTTPError.*",
            r".*status.*code.*"
        ]
    },
    ErrorCategory.PERMISSION: {
        "keywords": [
            "permission denied", "access denied", "readonly",
            "read-only", "cannot write", "not permitted", "chmod"
        ],
        "patterns": [
            r"PermissionError.*",
            r".*permission denied.*",
            r".*access denied.*"
        ]
    }
}


class IncidentAnalyzer:
    """Analyze and enhance incident information."""

    @staticmethod
    def analyze_incident_trends(recent_incidents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze trends from a list of recent incidents."""
        if not recent_incidents:
            return {
                "total_incidents": 0,
                "incidents_by_category": {},
                "incidents_by_severity": {},
                "incidents_over_time": [],
                "most_frequent_category": "N/A",
                "most_frequent_severity": "N/A",
                "trend": "stable" # stable, increasing, decreasing
            }

        total_incidents = len(recent_incidents)
        
        # Aggregate by category and severity
        incidents_by_category = {}
        incidents_by_severity = {}
        for incident in recent_incidents:
            category = incident.get("error_category", "UNKNOWN")
            severity = incident.get("severity", "LOW")
            incidents_by_category[category] = incidents_by_category.get(category, 0) + 1
            incidents_by_severity[severity] = incidents_by_severity.get(severity, 0) + 1

        # Time series analysis (e.g., last 7 days)
        incidents_over_time = {}
        seven_days_ago = datetime.now() - timedelta(days=7)
        for incident in recent_incidents:
            timestamp = datetime.fromisoformat(incident["timestamp"])
            if timestamp > seven_days_ago:
                date_str = timestamp.strftime('%Y-%m-%d')
                incidents_over_time[date_str] = incidents_over_time.get(date_str, 0) + 1
        
        # Format for chart
        sorted_dates = sorted(incidents_over_time.keys())
        time_series_data = [{"date": date, "count": incidents_over_time[date]} for date in sorted_dates]

        # Trend detection
        trend = "stable"
        if len(time_series_data) > 2:
            # Simple trend: compare first and last half averages
            mid_point = len(time_series_data) // 2
            first_half_avg = sum(d['count'] for d in time_series_data[:mid_point]) / (mid_point or 1)
            last_half_avg = sum(d['count'] for d in time_series_data[mid_point:]) / (len(time_series_data) - mid_point or 1)
            if last_half_avg > first_half_avg * 1.5:
                trend = "increasing"
            elif first_half_avg > last_half_avg * 1.5:
                trend = "decreasing"

        return {
            "total_incidents": total_incidents,
            "incidents_by_category": incidents_by_category,
            "incidents_by_severity": incidents_by_severity,
            "incidents_over_time": time_series_data,
            "most_frequent_category": max(incidents_by_category, key=incidents_by_category.get) if incidents_by_category else "N/A",
            "most_frequent_severity": max(incidents_by_severity, key=incidents_by_severity.get) if incidents_by_severity else "N/A",
            "trend": trend
        }
    
    @staticmethod
    def classify_error(error_log: str) -> ErrorCategory:
        """
        Classify error into category using patterns and keywords.
        
        Args:
            error_log: The error message to classify
            
        Returns:
            ErrorCategory: The classified category
        """
        if not error_log:
            return ErrorCategory.UNKNOWN
        
        log_lower = error_log.lower()
        
        # Check patterns first (more specific)
        for category, patterns_dict in ERROR_PATTERNS.items():
            for pattern in patterns_dict.get("patterns", []):
                if re.search(pattern, error_log, re.IGNORECASE):
                    return category
        
        # Then check keywords (more general)
        for category, patterns_dict in ERROR_PATTERNS.items():
            keywords = patterns_dict.get("keywords", [])
            if any(keyword in log_lower for keyword in keywords):
                return category
        
        return ErrorCategory.UNKNOWN
    
    @staticmethod
    def assess_severity(error_log: str, category: ErrorCategory) -> dict:
        """
        Assess incident severity based on keywords and category.
        
        Args:
            error_log: The error message
            category: The error category
            
        Returns:
            dict: Severity assessment with level and priority
        """
        log_lower = error_log.lower()
        
        # Critical indicators
        critical_keywords = [
            "data loss", "corruption", "shutdown", "fatal",
            "critical error", "catastrophic", "irreversible"
        ]
        
        # High indicators
        high_keywords = [
            "failed", "down", "unable", "broken", "cannot",
            "error", "exception", "denied", "refused", "unhandled"
        ]
        
        # Medium indicators
        medium_keywords = [
            "warning", "deprecated", "slow", "timeout",
            "limit", "exceeded", "invalid", "retrying"
        ]
        
        # Assess severity
        score = 0
        if any(kw in log_lower for kw in critical_keywords):
            score = 10
        elif "traceback (most recent call last)" in log_lower:
            score = 8 # Unhandled exceptions are high severity
        elif any(kw in log_lower for kw in high_keywords):
            score = 7
        elif any(kw in log_lower for kw in medium_keywords):
            score = 5
        else:
            score = 2

        # Adjust score based on category
        if category in [ErrorCategory.AUTHENTICATION, ErrorCategory.RESOURCE, ErrorCategory.DATABASE]:
            score = min(10, score + 1)

        if "404" in log_lower or "not found" in log_lower:
            score = max(1, score - 2) # Often less severe

        # Determine level from score
        if score >= 9:
            level = SeverityLevel.CRITICAL
        elif score >= 7:
            level = SeverityLevel.HIGH
        elif score >= 4:
            level = SeverityLevel.MEDIUM
        else:
            level = SeverityLevel.LOW
        
        return {
            "severity": level.value,
            "severity_score": score,  # 1-10 scale
        }
    
    @staticmethod
    def extract_root_causes(
        error_log: str, 
        category: ErrorCategory
    ) -> list[str]:
        """
        Extract likely root causes based on error category and content.
        
        Args:
            error_log: The error message
            category: The error category
            
        Returns:
            list[str]: List of probable root causes
        """
        log_lower = error_log.lower()

        cause_map = {
            ErrorCategory.DATABASE: [
                ("connection", "Database connection issue or timeout"),
                ("table|schema", "Missing or incorrect database table/schema"),
                ("auth|password", "Database authentication or credential mismatch"),
                ("constraint|foreign", "Database constraint or foreign key violation"),
                ("deadlock", "Database transaction deadlock"),
                ("pool", "Connection pool exhausted or misconfigured"),
            ],
            ErrorCategory.NETWORK: [
                ("timeout|timed out", "Service timeout - latency or service unresponsive"),
                ("dns", "DNS resolution failure - check domain/network"),
                ("refused|reset", "Remote service not accepting connections"),
                ("ssl|certificate", "SSL/TLS certificate validation failure"),
                ("broken pipe", "Network connection interrupted"),
            ],
            ErrorCategory.IMPORT: [
                ("no module|modulenotfound", "Required Python package not installed"),
                ("cannot import", "Circular dependency or module initialization error"),
                ("version", "Version mismatch between dependencies"),
            ],
            ErrorCategory.AUTHENTICATION: [
                ("expired", "Authentication token or session has expired"),
                ("invalid|malformed", "Malformed or invalid authentication format"),
                ("unauthorized|denied", "Invalid credentials or authentication token"),
            ],
            ErrorCategory.RESOURCE: [
                ("memory", "Out of memory - increase heap size or reduce load"),
                ("descriptor|too many open", "File descriptor limit reached - increase OS limits"),
                ("disk", "Disk space exhausted"),
            ],
            ErrorCategory.API: [
                ("429", "Rate limit exceeded - implement backoff strategy"),
                ("500|502|503", "Upstream service error or overload"),
                ("timeout", "API endpoint not responding in time"),
            ],
            ErrorCategory.PERMISSION: [
                ("permission|access denied", "File or directory permission issue"),
                ("privileges", "Process running with insufficient privileges"),
            ]
        }

        causes = []
        if category in cause_map:
            for keyword, cause in cause_map[category]:
                if re.search(keyword, log_lower):
                    causes.append(cause)
        
        # Default message if no specific causes found
        if not causes:
            causes = [f"Unable to determine specific root cause for {category.value} error - review error details"]
        
        return list(dict.fromkeys(causes)) # Return unique causes
    
    @staticmethod
    def get_affected_components(error_log: str) -> list[str]:
        """
        Extract affected components/services from error log.
        
        Args:
            error_log: The error message
            
        Returns:
            list[str]: List of affected components
        """
        components = set()
        log_lower = error_log.lower()
        
        # Check for common service names
        service_keywords = {
            "database": ["db", "postgres", "mysql", "sqlite", "mongodb", "sqlalchemy"],
            "cache": ["redis", "memcache", "cache"],
            "message_queue": ["kafka", "rabbitmq", "queue", "pubsub"],
            "api": ["api", "endpoint", "service", "http", "requests", "fastapi", "uvicorn"],
            "auth": ["auth", "oauth", "ldap", "saml", "jwt"],
            "storage": ["s3", "storage", "bucket", "blob", "filesystem"],
        }
        
        for component_type, keywords in service_keywords.items():
            if any(kw in log_lower for kw in keywords):
                components.add(component_type)

        # Extract file paths
        path_matches = re.findall(r'File "([^"]+)"', error_log)
        for path in path_matches:
            if 'site-packages' in path or 'dist-packages' in path:
                # Likely a library
                try:
                    lib_name = path.split('site-packages/')[1].split('/')[0]
                    components.add(f"lib:{lib_name}")
                except IndexError:
                    pass
            elif 'backend/' in path:
                components.add(path.split('backend/')[1])
        
        return sorted(list(components)) or ["unknown_component"]
    
    @staticmethod
    def calculate_incident_score(
        severity_score: int,
        confidence: float = 0.5
    ) -> dict:
        """
        Calculate incident impact, urgency, and complexity scores.
        
        Args:
            severity_score: Severity score (1-10)
            confidence: Confidence in diagnosis (0-1)
            
        Returns:
            dict: Scores for impact, urgency, and overall priority (normalized to 0-1)
        """
        # Normalize severity_score to 0-1 if it comes in as 1-10
        if severity_score > 1:
            severity_score = severity_score / 10.0
        
        # Impact = severity (0-1)
        impact_score = min(1.0, max(0.0, severity_score))
        
        # Urgency = based on severity (critical = urgent)
        urgency_score = min(1.0, max(0.0, severity_score))
        
        # Complexity = inverse of confidence (high confidence = low complexity)
        complexity_score = min(1.0, max(0.0, 1 - confidence))
        
        # Recovery = inverse of complexity
        recovery_score = min(1.0, max(0.0, 1 - complexity_score))
        
        # Priority = (Impact × Urgency) / (Complexity + 0.1) to avoid division by zero
        # Higher is more critical
        priority_score = (impact_score * urgency_score) / (complexity_score + 0.1)
        priority_score = min(1.0, max(0.0, priority_score))
        
        return {
            "impact_score": round(impact_score, 3),
            "urgency_score": round(urgency_score, 3),
            "complexity_score": round(complexity_score, 3),
            "recovery_score": round(recovery_score, 3),
            "priority_score": round(priority_score, 3),  # 0-1 scale
            "priority_level": (
                "CRITICAL" if priority_score >= 0.7 else
                "HIGH" if priority_score >= 0.5 else
                "MEDIUM" if priority_score >= 0.3 else
                "LOW"
            )
        }
    
    @staticmethod
    def get_recommended_actions(
        category: ErrorCategory,
        severity: str,
        root_causes: list[str]
    ) -> list[str]:
        """
        Get recommended actions based on error analysis.
        
        Args:
            category: Error category
            severity: Severity level
            root_causes: List of root causes
            
        Returns:
            list[str]: Recommended actions
        """
        actions = []
        
        # Always recommend checking the error details
        actions.append("1. Review full error message and stack trace for context")
        
        # Category-specific actions
        if category == ErrorCategory.DATABASE:
            actions.extend([
                "2. Verify database connectivity and credentials",
                "3. Check database server status and logs",
                "4. Validate schema and table existence",
                "5. Review recent database migrations or changes"
            ])
        
        elif category == ErrorCategory.NETWORK:
            actions.extend([
                "2. Check network connectivity (ping, DNS, traceroute)",
                "3. Verify service is running and accessible",
                "4. Check firewall rules and network policies",
                "5. Review service logs for errors"
            ])
        
        elif category == ErrorCategory.IMPORT:
            actions.extend([
                "2. Run: pip list to check installed packages",
                "3. Run: pip install <package> to install missing module",
                "4. Verify Python version compatibility",
                "5. Check requirements.txt for version specifications"
            ])
        
        elif category == ErrorCategory.AUTHENTICATION:
            actions.extend([
                "2. Verify API keys and tokens are valid",
                "3. Check token expiration time",
                "4. Refresh or regenerate credentials if needed",
                "5. Review authentication logs for failed attempts"
            ])
        
        elif category == ErrorCategory.RESOURCE:
            actions.extend([
                "2. Check system resource usage (memory, disk, CPU)",
                "3. Identify resource-consuming processes",
                "4. Scale up resources or optimize application",
                "5. Set up resource alerts and limits"
            ])
        
        # Add escalation if critical
        if severity == "CRITICAL":
            actions.append(f"\n🚨 CRITICAL INCIDENT: Notify on-call engineer immediately")
        
        return actions