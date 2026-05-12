"""
core/exceptions.py - الاستثناءات الخاصة بالنظام
==========================================
الاستثناءات الموجودة لضمان عدم انهيار النظام.
"""

class FireAIException(Exception):
    """الاستثناء الأساسي"""
    pass


class ExistentialRefusalError(FireAIException):
    """رفض وجودي - النظام يرفض كائن مستحيل منطقياً"""
    pass


class ResourceExhaustionError(FireAIException):
    """استنزاف الموارد - طلب موارد أكثر من المتاحة"""
    pass


class LogicalLoopDetectedError(FireAIException):
    """حلقة منطقية - اكتشاف حلقة لا نهائية"""
    pass


class CausalityViolationError(FireAIException):
    """انتهاك السببية - خرق التلسل الزمني"""
    pass


class StateSuperpositionError(FireAIException):
    """تراكب الحالات - عنصر في حالات متضادة"""
    pass


class OntologicalContradictionError(FireAIException):
    """تناقض أنطولوجي"""
    pass