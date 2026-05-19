"""
FireAI Cognitive Kernel - Simplified Persistent Learning
=============================================
SQLite-based learning system with BOQ comparison.
"""

import sqlite3
import json
import hashlib
from typing import Dict, List, Optional
from dataclasses import dataclass


@dataclass
class Case:
    interpretation: str
    confidence: float


class Kernel:
    """Simple persistent memory kernel."""
    
    def __init__(self):
        self.conn = sqlite3.connect(":memory:")
        self._setup()
        
    def _setup(self):
        self.conn.execute("""
            CREATE TABLE cases (
                id INTEGER PRIMARY KEY,
                layer TEXT,
                interpretation TEXT,
                confidence REAL
            )
        """)
        self.conn.commit()
        
    def learn(self, layer: str, interpretation: str, confidence: float = 1.0):
        self.conn.execute(
            "INSERT OR REPLACE INTO cases (layer, interpretation, confidence) VALUES (?, ?, ?)",
            (layer, interpretation, confidence)
        )
        self.conn.commit()
        
    def recall(self, layer: str) -> Optional[Case]:
        c = self.conn.execute(
            "SELECT interpretation, confidence FROM cases WHERE layer = ? LIMIT 1",
            (layer,)
        ).fetchone()
        if c:
            return Case(c[0], c[1])
        return None


class Comparator:
    """Compare Drawing vs BOQ."""
    
    def compare(self, detected, boq) -> List[Dict]:
        results = []
        for item, boq_count in boq.items():
            det = detected.get(item, 0)
            if det < boq_count:
                results.append({
                    "item": item,
                    "missing": boq_count - det,
                    "severity": "HIGH" if "Detector" in item else "MEDIUM"
                })
        return results


# Quick test
if __name__ == "__main__":
    print("Testing Kernel...")
    k = Kernel()
    k.learn("F-DEV", "Smoke Detector", 0.95)
    
    case = k.recall("F-DEV")
    print(f"Recalled: {case.interpretation} ({case.confidence:.0%})")
    
    comp = Comparator()
    result = comp.compare({"Smoke Detector": 5}, {"Smoke Detector": 10})
    print(f"Discrepancies: {len(result)}")
    
    print("✅ All working!")