from dataclasses import dataclass, field
from typing import List, Dict, Any
from core.risk_tensor.dsl_engine import DSLProgram, DSLRule, DSLDecay


@dataclass
class ASTTrigger:
    node_type: str
    trigger_state: str


@dataclass
class ASTCondition:
    condition_type: str
    target: str
    operator: str
    value: Any


@dataclass
class ASTEffect:
    effect_type: str
    target_type: str
    probability_factor: float
    decay_ref: str


@dataclass
class ASTPropagation:
    direction: str
    scope: str


@dataclass
class ASTRule:
    rule_id: str
    trigger: ASTTrigger
    conditions: List[ASTCondition]
    propagation: ASTPropagation
    effect: ASTEffect


@dataclass
class IRTriggerNode:
    node_id: str
    node_type: str
    trigger_state: str


@dataclass
class IRConditionNode:
    condition_type: str
    target: str
    operator: str
    value: Any


@dataclass
class IREffectNode:
    effect_type: str
    target_type: str
    probability_factor: float
    decay_function: str


@dataclass
class IRPropagationEdge:
    from_node: str
    to_node: str
    direction: str
    scope: str


@dataclass
class IRRuleGraph:
    rule_id: str
    trigger_node: IRTriggerNode
    condition_nodes: List[IRConditionNode]
    effect_node: IREffectNode
    propagation_edges: List[IRPropagationEdge]


@dataclass
class IntermediateRepresentation:
    rules: List[IRRuleGraph] = field(default_factory=list)
    decay_functions: Dict[str, DSLDecay] = field(default_factory=dict)
    global_execution_order: List[str] = field(default_factory=list)


class DSLCompiler:
    def __init__(self):
        self.ast_rules: List[ASTRule] = []
        self.ir_graphs: List[IRRuleGraph] = []
        self.validation_errors: List[str] = []

    def compile(self, program: DSLProgram) -> IntermediateRepresentation:
        self.ast_rules = []
        self.ir_graphs = []
        self.validation_errors = []

        for rule in program.rules:
            ast = self._parse_rule(rule)
            self.ast_rules.append(ast)

        valid_node_types = {n.node_type for n in program.nodes}
        self._validate(program, valid_node_types)

        if self.validation_errors:
            raise ValueError(f"DSL Compilation failed: {self.validation_errors}")

        for ast in self.ast_rules:
            ir_graph = self._build_ir_graph(ast)
            self.ir_graphs.append(ir_graph)

        execution_order = self._resolve_execution_order()
        decay_map = {d.decay_id: d for d in program.decays}

        return IntermediateRepresentation(
            rules=self.ir_graphs,
            decay_functions=decay_map,
            global_execution_order=execution_order
        )

    def _parse_rule(self, rule: DSLRule) -> ASTRule:
        trigger = ASTTrigger(node_type=rule.trigger_type, trigger_state=rule.trigger_state)
        conditions = []
        for cond in rule.conditions:
            conditions.append(ASTCondition(
                condition_type=cond.get("type", "zone_type"),
                target=cond.get("target", "zone"),
                operator=cond.get("operator", "=="),
                value=cond.get("value", "generic")
            ))
        propagation = ASTPropagation(direction=rule.propagation_direction, scope=rule.scope)
        effect = ASTEffect(
            effect_type=rule.effect_type,
            target_type=rule.target_type,
            probability_factor=rule.probability_factor,
            decay_ref=rule.decay_function_ref
        )
        return ASTRule(rule_id=rule.rule_id, trigger=trigger, conditions=conditions, propagation=propagation, effect=effect)

    def _validate(self, program: DSLProgram, valid_node_types: set):
        for rule in program.rules:
            if rule.trigger_type not in valid_node_types:
                self.validation_errors.append(f"Rule {rule.rule_id}: trigger type '{rule.trigger_type}' not in node types")
            if rule.target_type not in valid_node_types:
                self.validation_errors.append(f"Rule {rule.rule_id}: target type '{rule.target_type}' not in node types")
            if rule.decay_function_ref not in [d.decay_id for d in program.decays]:
                self.validation_errors.append(f"Rule {rule.rule_id}: decay '{rule.decay_function_ref}' not found")

    def _build_ir_graph(self, ast: ASTRule) -> IRRuleGraph:
        trigger_node = IRTriggerNode(
            node_id=f"trigger_{ast.rule_id}",
            node_type=ast.trigger.node_type,
            trigger_state=ast.trigger.trigger_state
        )
        condition_nodes = []
        for cond in ast.conditions:
            condition_nodes.append(IRConditionNode(
                condition_type=cond.condition_type,
                target=cond.target,
                operator=cond.operator,
                value=cond.value
            ))
        effect_node = IREffectNode(
            effect_type=ast.effect.effect_type,
            target_type=ast.effect.target_type,
            probability_factor=ast.effect.probability_factor,
            decay_function=ast.effect.decay_ref
        )
        propagation_edges = [IRPropagationEdge(
            from_node=trigger_node.node_id,
            to_node=effect_node.effect_type,
            direction=ast.propagation.direction,
            scope=ast.propagation.scope
        )]
        return IRRuleGraph(
            rule_id=ast.rule_id,
            trigger_node=trigger_node,
            condition_nodes=condition_nodes,
            effect_node=effect_node,
            propagation_edges=propagation_edges
        )

    def _resolve_execution_order(self) -> List[str]:
        order = []
        for ir in self.ir_graphs:
            if "POWER" in ir.rule_id:
                order.insert(0, ir.rule_id)
            elif "PANEL" in ir.rule_id:
                if ir.rule_id not in order:
                    order.append(ir.rule_id)
            else:
                if ir.rule_id not in order:
                    order.append(ir.rule_id)
        return order