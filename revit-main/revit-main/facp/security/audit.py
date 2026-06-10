"""
FACP Audit Logging System
"""
from typing import Dict, Any, List
import time
import json
import threading
from datetime import datetime
from enum import Enum
import os
from pathlib import Path


class EventType(Enum):
    """Types of audit events"""
    REQUEST_RECEIVED = "request_received"
    REQUEST_VALIDATED = "request_validated"
    AUTHENTICATION_ATTEMPT = "authentication_attempt"
    AUTHORIZATION_CHECK = "authorization_check"
    ENGINE_EXECUTION = "engine_execution"
    RESPONSE_SENT = "response_sent"
    SECURITY_VIOLATION = "security_violation"
    ERROR_OCCURRED = "error_occurred"


class EventLogger:
    """
    Basic event logging system
    """
    def __init__(self, log_file: str = "facp_events.log", max_log_size: int = 10 * 1024 * 1024):  # 10MB
        self.log_file = log_file
        self.max_log_size = max_log_size
        self.lock = threading.Lock()
        self._ensure_log_directory()

    def _ensure_log_directory(self):
        """Ensure log directory exists"""
        log_path = Path(self.log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

    def log_event(self, event_type: EventType, details: Dict[str, Any], severity: str = "INFO"):
        """Log an event"""
        with self.lock:
            event = {
                "timestamp": datetime.utcnow().isoformat(),
                "event_type": event_type.value,
                "severity": severity,
                "details": details
            }
            
            # Rotate log if too large
            if self._log_file_exceeds_size():
                self._rotate_log()
            
            # Write event to log file
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(event) + "\n")

    def _log_file_exceeds_size(self) -> bool:
        """Check if log file exceeds size limit"""
        try:
            return os.path.getsize(self.log_file) > self.max_log_size
        except OSError:
            return False

    def _rotate_log(self):
        """Rotate log file"""
        try:
            rotated_name = f"{self.log_file}.old"
            if os.path.exists(rotated_name):
                os.remove(rotated_name)
            os.rename(self.log_file, rotated_name)
        except OSError:
            pass  # If rotation fails, continue with current log

    def read_recent_events(self, count: int = 10) -> List[Dict[str, Any]]:
        """Read recent events from log file"""
        try:
            with open(self.log_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
                events = []
                for line in lines[-count:]:
                    try:
                        events.append(json.loads(line.strip()))
                    except json.JSONDecodeError:
                        continue
                return events
        except FileNotFoundError:
            return []


class AuditLogger:
    """
    Specialized audit logger for security and compliance
    """
    def __init__(self, audit_file: str = "facp_audit.log"):
        self.event_logger = EventLogger(audit_file)
        self.session_tracking = {}  # track ongoing sessions
        self.compliance_tracking = {}  # track compliance requirements

    def log_authentication(self, user_id: str, success: bool, source_ip: str = "unknown"):
        """Log authentication event"""
        details = {
            "user_id": user_id,
            "success": success,
            "source_ip": source_ip,
            "timestamp": time.time()
        }
        
        severity = "INFO" if success else "WARNING"
        event_type = EventType.AUTHENTICATION_ATTEMPT
        
        self.event_logger.log_event(event_type, details, severity)
        
        # Track failed attempts for security analysis
        if not success:
            self._track_failed_auth(user_id, source_ip)

    def log_authorization(self, user_id: str, method: str, allowed: bool, permissions: List[str]):
        """Log authorization check"""
        details = {
            "user_id": user_id,
            "method": method,
            "allowed": allowed,
            "permissions": permissions,
            "timestamp": time.time()
        }
        
        severity = "INFO" if allowed else "WARNING"
        event_type = EventType.AUTHORIZATION_CHECK
        
        self.event_logger.log_event(event_type, details, severity)

    def log_request_processed(self, request_id: str, user_id: str, method: str, risk_level: str):
        """Log processed request"""
        details = {
            "request_id": request_id,
            "user_id": user_id,
            "method": method,
            "risk_level": risk_level,
            "timestamp": time.time()
        }
        
        self.event_logger.log_event(EventType.REQUEST_VALIDATED, details, "INFO")

    def log_engine_execution(self, request_id: str, user_id: str, method: str, 
                           execution_time: float, success: bool):
        """Log engine execution"""
        details = {
            "request_id": request_id,
            "user_id": user_id,
            "method": method,
            "execution_time_ms": execution_time,
            "success": success,
            "timestamp": time.time()
        }
        
        severity = "INFO" if success else "ERROR"
        event_type = EventType.ENGINE_EXECUTION
        
        self.event_logger.log_event(event_type, details, severity)

    def log_security_violation(self, violation_type: str, details: Dict[str, Any]):
        """Log security violation"""
        details["violation_type"] = violation_type
        details["timestamp"] = time.time()
        
        self.event_logger.log_event(EventType.SECURITY_VIOLATION, details, "CRITICAL")

    def log_compliance_check(self, check_type: str, resource: str, compliant: bool, details: Dict[str, Any]):
        """Log compliance check"""
        compliance_details = {
            "check_type": check_type,
            "resource": resource,
            "compliant": compliant,
            "details": details,
            "timestamp": time.time()
        }
        
        severity = "INFO" if compliant else "WARNING"
        self.event_logger.log_event(EventType.REQUEST_VALIDATED, compliance_details, severity)

    def _track_failed_auth(self, user_id: str, source_ip: str):
        """Track failed authentication attempts for security analysis"""
        key = f"{user_id}:{source_ip}"
        if key not in self.session_tracking:
            self.session_tracking[key] = []
        
        self.session_tracking[key].append(time.time())
        
        # Clean up old entries (older than 1 hour)
        cutoff = time.time() - 3600
        self.session_tracking[key] = [t for t in self.session_tracking[key] if t > cutoff]

    def check_brute_force(self, user_id: str, source_ip: str, threshold: int = 5) -> bool:
        """Check for potential brute force attack"""
        key = f"{user_id}:{source_ip}"
        if key not in self.session_tracking:
            return False
        
        recent_attempts = [t for t in self.session_tracking[key] if t > time.time() - 300]  # 5 minutes
        return len(recent_attempts) >= threshold

    def get_audit_summary(self) -> Dict[str, Any]:
        """Get audit summary statistics"""
        recent_events = self.event_logger.read_recent_events(100)
        
        stats = {
            "total_events": len(recent_events),
            "by_type": {},
            "by_severity": {},
            "recent_security_violations": [],
            "failed_auth_attempts": 0
        }
        
        for event in recent_events:
            # Count by event type
            event_type = event.get("event_type", "unknown")
            stats["by_type"][event_type] = stats["by_type"].get(event_type, 0) + 1
            
            # Count by severity
            severity = event.get("severity", "unknown")
            stats["by_severity"][severity] = stats["by_severity"].get(severity, 0) + 1
            
            # Track security violations
            if event_type == EventType.SECURITY_VIOLATION.value:
                stats["recent_security_violations"].append(event)
            
            # Count failed authentications
            if (event_type == EventType.AUTHENTICATION_ATTEMPT.value and 
                event.get("details", {}).get("success") is False):
                stats["failed_auth_attempts"] += 1
        
        return stats

    def export_audit_report(self, output_file: str, days: int = 7) -> bool:
        """Export audit report for compliance"""
        try:
            cutoff = time.time() - (days * 24 * 3600)
            recent_events = self.event_logger.read_recent_events(1000)  # Large number
            
            # Filter events by date
            filtered_events = [
                event for event in recent_events 
                if datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00")).timestamp() > cutoff
            ]
            
            report = {
                "report_date": datetime.utcnow().isoformat(),
                "period_days": days,
                "total_events": len(filtered_events),
                "events": filtered_events,
                "summary": self.get_audit_summary()
            }
            
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, default=str)
            
            return True
        except Exception:
            return False