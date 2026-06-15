"""
Audit Logging System for Distributed FACP System
"""
import hashlib
import json
import os
import threading
import time
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List


class EventType(Enum):
    """Types of audit events in distributed system"""
    REQUEST_RECEIVED = "request_received"
    REQUEST_VALIDATED = "request_validated"
    AUTHENTICATION_ATTEMPT = "authentication_attempt"
    AUTHORIZATION_CHECK = "authorization_check"
    ENGINE_EXECUTION = "engine_execution"
    NODE_COMMUNICATION = "node_communication"
    RESPONSE_SENT = "response_sent"
    SECURITY_VIOLATION = "security_violation"
    ERROR_OCCURRED = "error_occurred"
    CLUSTER_SYNC = "cluster_sync"
    IDENTITY_PROVISIONING = "identity_provisioning"


class DistributedEventLogger:
    """
    Event logging system for distributed environment
    """
    def __init__(self, log_file: str = "facp_distributed_events.log", max_log_size: int = 10 * 1024 * 1024):  # 10MB
        self.log_file = log_file
        self.max_log_size = max_log_size
        self.lock = threading.Lock()
        self._ensure_log_directory()
        self.node_id = f"node_{int(time.time())}_{os.getpid()}"

    def _ensure_log_directory(self):
        """Ensure log directory exists"""
        log_path = Path(self.log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

    def log_event(self, event_type: EventType, details: Dict[str, Any], severity: str = "INFO", source_node: str = None):
        """Log an event in distributed context"""
        with self.lock:
            event = {
                "timestamp": datetime.utcnow().isoformat(),
                "event_type": event_type.value,
                "severity": severity,
                "source_node": source_node or self.node_id,
                "details": details,
                "event_id": hashlib.sha256(f"{time.time()}{event_type.value}{details}".encode()).hexdigest()[:16]
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
            rotated_name = f"{self.log_file}.{int(time.time())}"
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
    Specialized audit logger for security and compliance in distributed system
    """
    def __init__(self, audit_file: str = "facp_distributed_audit.log"):
        self.event_logger = DistributedEventLogger(audit_file)
        self.session_tracking = {}  # track ongoing sessions
        self.compliance_tracking = {}  # track compliance requirements
        self.node_communication_log = {}  # track communication between nodes
        self.security_alerts = []  # alerts that need attention

    def log_authentication(self, user_id: str, success: bool, source_node: str = "unknown",
                          target_node: str = "unknown"):
        """Log authentication event in distributed context"""
        details = {
            "user_id": user_id,
            "success": success,
            "source_node": source_node,
            "target_node": target_node,
            "timestamp": time.time()
        }

        severity = "INFO" if success else "WARNING"
        event_type = EventType.AUTHENTICATION_ATTEMPT

        self.event_logger.log_event(event_type, details, severity, source_node)

        # Track failed attempts for security analysis
        if not success:
            self._track_failed_auth(user_id, source_node)

    def log_authorization(self, user_id: str, method: str, allowed: bool, permissions: List[str],
                         source_node: str = "unknown", target_node: str = "unknown"):
        """Log authorization check in distributed context"""
        details = {
            "user_id": user_id,
            "method": method,
            "allowed": allowed,
            "permissions": permissions,
            "source_node": source_node,
            "target_node": target_node,
            "timestamp": time.time()
        }

        severity = "INFO" if allowed else "WARNING"
        event_type = EventType.AUTHORIZATION_CHECK

        self.event_logger.log_event(event_type, details, severity, source_node)

    def log_request_processed(self, request_id: str, user_id: str, method: str, risk_level: str,
                            source_node: str = "unknown", target_node: str = "unknown"):
        """Log processed request in distributed context"""
        details = {
            "request_id": request_id,
            "user_id": user_id,
            "method": method,
            "risk_level": risk_level,
            "source_node": source_node,
            "target_node": target_node,
            "timestamp": time.time()
        }

        self.event_logger.log_event(EventType.REQUEST_VALIDATED, details, "INFO", source_node)

    def log_engine_execution(self, request_id: str, user_id: str, method: str,
                           execution_time: float, success: bool, source_node: str = "unknown"):
        """Log engine execution in distributed context"""
        details = {
            "request_id": request_id,
            "user_id": user_id,
            "method": method,
            "execution_time_ms": execution_time,
            "success": success,
            "source_node": source_node,
            "timestamp": time.time()
        }

        severity = "INFO" if success else "ERROR"
        event_type = EventType.ENGINE_EXECUTION

        self.event_logger.log_event(event_type, details, severity, source_node)

    def log_node_communication(self, from_node: str, to_node: str, message_type: str,
                             success: bool, latency: float, request_id: str = None):
        """Log communication between nodes"""
        details = {
            "from_node": from_node,
            "to_node": to_node,
            "message_type": message_type,
            "success": success,
            "latency_ms": latency,
            "request_id": request_id,
            "timestamp": time.time()
        }

        severity = "INFO" if success else "WARNING"
        event_type = EventType.NODE_COMMUNICATION

        self.event_logger.log_event(event_type, details, severity, from_node)

        # Track communication patterns
        comm_key = f"{from_node}->{to_node}"
        if comm_key not in self.node_communication_log:
            self.node_communication_log[comm_key] = []
        self.node_communication_log[comm_key].append(details)

    def log_security_violation(self, violation_type: str, details: Dict[str, Any],
                             source_node: str = "unknown"):
        """Log security violation in distributed context"""
        details["violation_type"] = violation_type
        details["source_node"] = source_node
        details["timestamp"] = time.time()

        self.event_logger.log_event(EventType.SECURITY_VIOLATION, details, "CRITICAL", source_node)

        # Add to alerts
        self.security_alerts.append({
            "violation_type": violation_type,
            "details": details,
            "alert_time": time.time()
        })

    def log_compliance_check(self, check_type: str, resource: str, compliant: bool,
                           details: Dict[str, Any], node_context: str = "unknown"):
        """Log compliance check in distributed context"""
        compliance_details = {
            "check_type": check_type,
            "resource": resource,
            "compliant": compliant,
            "details": details,
            "node_context": node_context,
            "timestamp": time.time()
        }

        severity = "INFO" if compliant else "WARNING"
        self.event_logger.log_event(EventType.REQUEST_VALIDATED, compliance_details, severity, node_context)

    def log_cluster_sync(self, sync_operation: str, nodes_involved: List[str],
                        success: bool, sync_time: float):
        """Log cluster synchronization events"""
        details = {
            "sync_operation": sync_operation,
            "nodes_involved": nodes_involved,
            "success": success,
            "sync_time_ms": sync_time,
            "timestamp": time.time()
        }

        severity = "INFO" if success else "WARNING"
        event_type = EventType.CLUSTER_SYNC

        self.event_logger.log_event(event_type, details, severity, "cluster_coordinator")

    def _track_failed_auth(self, user_id: str, source_node: str):
        """Track failed authentication attempts for security analysis"""
        key = f"{user_id}:{source_node}"
        if key not in self.session_tracking:
            self.session_tracking[key] = []

        self.session_tracking[key].append(time.time())

        # Clean up old entries (older than 1 hour)
        cutoff = time.time() - 3600
        self.session_tracking[key] = [t for t in self.session_tracking[key] if t > cutoff]

    def check_brute_force(self, user_id: str, source_node: str, threshold: int = 5) -> bool:
        """Check for potential brute force attack"""
        key = f"{user_id}:{source_node}"
        if key not in self.session_tracking:
            return False

        recent_attempts = [t for t in self.session_tracking[key] if t > time.time() - 300]  # 5 minutes
        return len(recent_attempts) >= threshold

    def get_audit_summary(self) -> Dict[str, Any]:
        """Get audit summary statistics for distributed system"""
        recent_events = self.event_logger.read_recent_events(100)

        stats = {
            "total_events": len(recent_events),
            "by_type": {},
            "by_severity": {},
            "by_node": {},
            "recent_security_violations": [],
            "failed_auth_attempts": 0,
            "node_communications": len(self.node_communication_log),
            "security_alerts": len(self.security_alerts),
            "active_sessions": len(self.session_tracking)
        }

        for event in recent_events:
            # Count by event type
            event_type = event.get("event_type", "unknown")
            stats["by_type"][event_type] = stats["by_type"].get(event_type, 0) + 1

            # Count by severity
            severity = event.get("severity", "unknown")
            stats["by_severity"][severity] = stats["by_severity"].get(severity, 0) + 1

            # Count by node
            node = event.get("source_node", "unknown")
            stats["by_node"][node] = stats["by_node"].get(node, 0) + 1

            # Track security violations
            if event_type == EventType.SECURITY_VIOLATION.value:
                stats["recent_security_violations"].append(event)

            # Count failed authentications
            if (event_type == EventType.AUTHENTICATION_ATTEMPT.value and
                event.get("details", {}).get("success") is False):
                stats["failed_auth_attempts"] += 1

        return stats

    def export_audit_report(self, output_file: str, days: int = 7) -> bool:
        """Export audit report for compliance in distributed system"""
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
                "node_communication_summary": {
                    node_pair: len(logs) for node_pair, logs in self.node_communication_log.items()
                },
                "security_alerts": self.security_alerts,
                "summary": self.get_audit_summary()
            }

            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, default=str)

            return True
        except Exception as e:
            print(f"Error exporting audit report: {e}")
            return False

    def cleanup_old_alerts(self, max_age_hours: int = 24):
        """Clean up old security alerts"""
        cutoff = time.time() - (max_age_hours * 3600)
        self.security_alerts = [alert for alert in self.security_alerts if alert["alert_time"] > cutoff]

    def generate_security_insights(self) -> Dict[str, Any]:
        """Generate security insights from audit logs"""
        summary = self.get_audit_summary()

        insights = {
            "top_talkers": sorted(summary["by_node"].items(), key=lambda x: x[1], reverse=True)[:5],
            "most_common_violations": sorted(
                [(k, v) for k, v in summary["by_type"].items() if "violation" in k.lower()],
                key=lambda x: x[1], reverse=True
            ),
            "potential_security_risks": [],
            "recommendations": []
        }

        # Identify potential security risks
        for node, count in summary["by_node"].items():
            if count > 1000:  # Arbitrary threshold
                insights["potential_security_risks"].append(f"High activity from node {node}: {count} events")

        # Add recommendations
        if summary["failed_auth_attempts"] > 10:
            insights["recommendations"].append("Consider implementing rate limiting for authentication attempts")

        if summary["security_alerts"] > 5:
            insights["recommendations"].append("Review security configuration and access controls")

        return insights
