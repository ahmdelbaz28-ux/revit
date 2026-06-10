"""
FACP Execution State Machine
"""
from enum import Enum
from typing import Dict, Any, Optional
import time
import threading
from datetime import datetime


class ExecutionState(Enum):
    """States in the FACP execution lifecycle"""
    RECEIVED = "received"
    VALIDATED = "validated"
    ROUTED = "routed"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"


class ExecutionStateMachine:
    """
    State machine that tracks execution progress through FACP layers
    """
    def __init__(self):
        self.requests = {}  # request_id -> state_info
        self.state_transitions = {}  # request_id -> list of state transitions
        self.lock = threading.RLock()  # Use RLock for recursive locking if needed

    def create_request_state(self, request_id: str, initial_data: Dict[str, Any] = None):
        """Create initial state for a request"""
        with self.lock:
            self.requests[request_id] = {
                "current_state": ExecutionState.RECEIVED,
                "initial_data": initial_data or {},
                "created_at": time.time(),
                "state_history": [{
                    "state": ExecutionState.RECEIVED.value,
                    "timestamp": time.time(),
                    "details": "Request received"
                }],
                "transition_times": {
                    ExecutionState.RECEIVED.value: time.time()
                }
            }
            self.state_transitions[request_id] = []

    def transition_to(self, request_id: str, new_state: ExecutionState, 
                     details: str = "", additional_data: Dict[str, Any] = None) -> bool:
        """Transition request to a new state"""
        with self.lock:
            if request_id not in self.requests:
                return False

            current_state = self.requests[request_id]["current_state"]
            
            # Validate state transition (simple validation - can be expanded)
            valid_transitions = {
                ExecutionState.RECEIVED: [ExecutionState.VALIDATED, ExecutionState.FAILED],
                ExecutionState.VALIDATED: [ExecutionState.ROUTED, ExecutionState.FAILED],
                ExecutionState.ROUTED: [ExecutionState.EXECUTING, ExecutionState.FAILED],
                ExecutionState.EXECUTING: [ExecutionState.COMPLETED, ExecutionState.FAILED],
                ExecutionState.COMPLETED: [],
                ExecutionState.FAILED: []
            }
            
            if new_state not in valid_transitions.get(current_state, []):
                if current_state != new_state:  # Allow staying in same state
                    return False

            # Update state
            old_state = current_state
            self.requests[request_id]["current_state"] = new_state
            self.requests[request_id]["last_transition"] = time.time()
            
            # Record transition
            transition_info = {
                "from_state": old_state.value,
                "to_state": new_state.value,
                "timestamp": time.time(),
                "details": details,
                "additional_data": additional_data or {}
            }
            
            self.requests[request_id]["state_history"].append(transition_info)
            self.requests[request_id]["transition_times"][new_state.value] = time.time()
            
            # Record in transition log
            self.state_transitions[request_id].append(transition_info)
            
            return True

    def get_current_state(self, request_id: str) -> Optional[ExecutionState]:
        """Get current state of a request"""
        with self.lock:
            if request_id not in self.requests:
                return None
            return self.requests[request_id]["current_state"]

    def get_state_history(self, request_id: str) -> list:
        """Get state transition history for a request"""
        with self.lock:
            if request_id not in self.requests:
                return []
            return self.requests[request_id]["state_history"]

    def get_execution_trace(self, request_id: str) -> Dict[str, Any]:
        """Get execution trace for a request"""
        with self.lock:
            if request_id not in self.requests:
                return {}
                
            request_info = self.requests[request_id]
            state_history = request_info["state_history"]
            
            # Calculate timing information
            timing_info = {}
            for i in range(len(state_history) - 1):
                current = state_history[i]
                next_state = state_history[i + 1]
                duration = next_state["timestamp"] - current["timestamp"]
                timing_info[f"{current['state']}_to_{next_state['state']}"] = duration
            
            return {
                "request_id": request_id,
                "final_state": request_info["current_state"].value,
                "states_visited": [entry["state"] for entry in state_history],
                "timing": timing_info,
                "total_duration": time.time() - request_info["created_at"],
                "state_history": state_history
            }

    def is_terminal_state(self, request_id: str) -> bool:
        """Check if request is in a terminal state"""
        state = self.get_current_state(request_id)
        return state in [ExecutionState.COMPLETED, ExecutionState.FAILED]

    def cleanup_request(self, request_id: str):
        """Clean up request state after completion"""
        with self.lock:
            if request_id in self.requests:
                del self.requests[request_id]
            if request_id in self.state_transitions:
                del self.state_transitions[request_id]

    def get_statistics(self) -> Dict[str, Any]:
        """Get execution statistics"""
        with self.lock:
            stats = {
                "total_requests": len(self.requests),
                "by_state": {},
                "active_requests": 0,
                "completed_requests": 0,
                "failed_requests": 0
            }
            
            for req_id, req_info in self.requests.items():
                state_val = req_info["current_state"].value
                stats["by_state"][state_val] = stats["by_state"].get(state_val, 0) + 1
                
                if req_info["current_state"] not in [ExecutionState.COMPLETED, ExecutionState.FAILED]:
                    stats["active_requests"] += 1
                elif req_info["current_state"] == ExecutionState.COMPLETED:
                    stats["completed_requests"] += 1
                elif req_info["current_state"] == ExecutionState.FAILED:
                    stats["failed_requests"] += 1
                    
            return stats

    def validate_state_sequence(self, request_id: str) -> tuple[bool, list]:
        """Validate that state transitions followed proper sequence"""
        with self.lock:
            if request_id not in self.requests:
                return False, ["Request not found"]
            
            history = self.requests[request_id]["state_history"]
            states = [entry["state"] for entry in history]
            
            # Define valid sequence
            valid_sequence = [
                ExecutionState.RECEIVED.value,
                ExecutionState.VALIDATED.value,
                ExecutionState.ROUTED.value,
                ExecutionState.EXECUTING.value,
                ExecutionState.COMPLETED.value  # or ExecutionState.FAILED.value
            ]
            
            # Check if states follow valid sequence
            valid_pos = 0
            errors = []
            
            for state in states:
                # Look for this state in valid sequence starting from current position
                found = False
                for i in range(valid_pos, len(valid_sequence)):
                    if state == valid_sequence[i]:
                        valid_pos = i + 1
                        found = True
                        break
                
                if not found:
                    errors.append(f"Invalid state transition: {state} not in expected sequence")
            
            return len(errors) == 0, errors


class StateMachineValidator:
    """Helper class to validate state machine behavior"""
    
    @staticmethod
    def validate_request_flow(execution_sm: ExecutionStateMachine, request_id: str) -> tuple[bool, str]:
        """Validate that a request followed proper flow"""
        is_valid, errors = execution_sm.validate_state_sequence(request_id)
        
        if not is_valid:
            return False, f"Invalid state sequence: {'; '.join(errors)}"
        
        current_state = execution_sm.get_current_state(request_id)
        if current_state in [ExecutionState.COMPLETED, ExecutionState.FAILED]:
            return True, "Request completed successfully"
        else:
            return True, f"Request still in progress: {current_state.value}"