from dataclasses import dataclass
from typing import List, Dict, Any


@dataclass
class Violation:
    rule_id: str
    severity: str
    room_id: str
    message: str
    recommendation: str


class Rule:
    rule_id: str = ""
    source: str = ""
    version: str = ""
    severity: str = "MEDIUM"
    category: str = ""
    description: str = ""
    applicable_room_types: List[str] = None

    def __init__(self):
        if self.applicable_room_types is None:
            self.applicable_room_types = []

    def evaluate(self, context: Any) -> List[Violation]:
        raise NotImplementedError

    def is_applicable(self, room_type: str) -> bool:
        if not self.applicable_room_types:
            return True
        return room_type in self.applicable_room_types

    def get_metadata(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "source": self.source,
            "version": self.version,
            "severity": self.severity,
            "category": self.category,
            "description": self.description
        }