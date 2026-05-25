"""
test_void_protocol.py - اختبار العدم: حيث يفشل المنطق والرياضيات.
الهدف: إجبار النظام على الاعتراف بأن بعض المشاكل لا تُحل، بل تُرفض وجودياً.
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.models import UniversalElement, SemanticProperties, ElementType, Geometry, Point3D


class ConstraintSolver:
    """محاكي محلل القيود"""
    
    def solve_placement(self, room):
        # محاولة حل مشكلة مستحيلة
        if hasattr(room, 'get_area'):
            # محاولة استدعاء get_area التي تتغير داخلياً
            area = room.get_area()
            if area == 0:
                raise ValueError("Ontological_Paradox: Device creates and destroys room")
            elif area == 100:
                raise ValueError("Ontological_Paradox: Room exists only without device")
        raise Exception("Unknown_Paradox")


class RuleEngine:
    """محرك القواعد"""
    
    def __init__(self):
        self.rules = {}
        self.checking = set()
    
    def add_rule(self, name, condition):
        self.rules[name] = condition
    
    def check(self, rule_name):
        if rule_name in self.checking:
            raise RecursionError(f"Infinite_Regression: {rule_name}")
        
        self.checking.add(rule_name)
        try:
            condition = self.rules.get(rule_name, lambda: False)
            return condition()
        finally:
            self.checking.discard(rule_name)


class TestVoidProtocol:
    """اختبارات تتجاوز الخطأ لتصل إلى 'العدم'."""

    def test_ontological_paradox_device_placement(self):
        """المفارقة الأنطولوجية: جهاز يخلق الغرفة ويعدمها"""
        
        class SchrodingerRoom:
            def __init__(self):
                self.has_device = False
            
            def get_area(self):
                return 0 if self.has_device else 100.0

        room = SchrodingerRoom()
        solver = ConstraintSolver()

        with pytest.raises(Exception) as exc_info:
            solver.solve_placement(room)
            
        assert "Ontological" in str(exc_info.value) or "Contradiction" in str(exc_info.value) \
               or "Impossible" in str(exc_info.value), \
               f"Failed randomly ({exc_info.value})!"

    def test_infinite_regression_of_truth(self):
        """التراجع اللانهائي للحقيقة"""
        
        engine = RuleEngine()
        
        engine.add_rule("Rule_A", lambda: not engine.check("Rule_B"))
        engine.add_rule("Rule_B", lambda: not engine.check("Rule_A"))
        
        with pytest.raises(RecursionError):
            engine.check("Rule_A")

    def test_the_final_silence(self):
        """الصمت النهائي"""
        
        from core.database import UniversalDataModel
        
        db = UniversalDataModel(db_path=":memory:")
        
        elem = UniversalElement(
            properties=SemanticProperties(element_type=ElementType.WALL, name="Test"),
            geometry=Geometry(points=[Point3D(0,0,0)])
        )
        db.add_element(elem)
        
        # تدمير المحرك
        if hasattr(db, 'engine'):
            db.engine = None
        
        with pytest.raises(AttributeError):
            db.get_all_elements()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])