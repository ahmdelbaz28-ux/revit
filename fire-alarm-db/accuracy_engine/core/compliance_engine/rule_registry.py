from typing import List
from core.compliance_engine.base_rule import Rule
from core.compliance_engine.rules.spacing_rule import DetectorSpacingRule
from core.compliance_engine.rules.coverage_rule import CoverageRule
from core.compliance_engine.rules.redundancy_rule import RedundancyRule


class RuleRegistry:
    _rules: List[Rule] = []

    @classmethod
    def initialize(cls):
        if not cls._rules:
            cls._rules = [
                DetectorSpacingRule(),
                CoverageRule(),
                RedundancyRule(),
            ]

    @classmethod
    def get_all_rules(cls) -> List[Rule]:
        cls.initialize()
        return cls._rules

    @classmethod
    def get_rules_by_category(cls, category: str) -> List[Rule]:
        cls.initialize()
        return [r for r in cls._rules if r.category == category]

    @classmethod
    def get_rules_by_severity(cls, severity: str) -> List[Rule]:
        cls.initialize()
        return [r for r in cls._rules if r.severity == severity]

    @classmethod
    def get_rule_by_id(cls, rule_id: str) -> Rule:
        cls.initialize()
        for r in cls._rules:
            if r.rule_id == rule_id:
                return r
        return None

    @classmethod
    def add_rule(cls, rule: Rule):
        cls.initialize()
        cls._rules.append(rule)

    @classmethod
    def get_all_metadata(cls) -> List[dict]:
        cls.initialize()
        return [r.get_metadata() for r in cls._rules]