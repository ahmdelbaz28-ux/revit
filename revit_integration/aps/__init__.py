"""
ETAP-AI-WORK Revit Integration APS Module
=========================================

Autodesk Platform Services integration components.

Principal Software Architect: Eng. Ahmed Elbaz
"""
from .auth_service import APSAuthService
from .data_exchange import APSDataExchange

# Note: APSModelDerivative is planned but not yet implemented
# from .model_derivative import APSModelDerivative

__all__ = [
    'APSAuthService',
    'APSDataExchange',
    # 'APSModelDerivative'
]