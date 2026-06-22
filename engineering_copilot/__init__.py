"""
ETAP-AI-WORK Engineering Copilot - Main Module
============================================

Principal Software Architect: Eng. Ahmed Elbaz
Lead Solution Architect: Eng. Ahmed Elbaz
Principal Autodesk Integration Engineer: Eng. Ahmed Elbaz
"""
from .models import (
    BaseEntity, Coordinates, UnifiedEngineeringModel,
    Project, Building, Level, Room, ElectricalRoom,
    Panel, Switchboard, Bus, Transformer, Generator,
    Cable, Breaker, Load, Motor, Relay, ProtectionDevice,
    Conduit, Tray, Equipment, Annotation
)
from .ai_agent.ai_agent import AICopilot, EngineeringIntentProcessor
from .translation_engine.translation_engine import TranslationEngine
from .connectors.autocad_connector import AutoCADConnector
from .connectors.revit_connector import RevitConnector
from .connectors.etap_connector import ETAPConnector
from .mcp_server.mcp_server import mcp_server, get_mcp_app

__version__ = "1.0.0"
__author__ = "Eng. Ahmed Elbaz"
__all__ = [
    # Models
    'BaseEntity', 'Coordinates', 'UnifiedEngineeringModel',
    'Project', 'Building', 'Level', 'Room', 'ElectricalRoom',
    'Panel', 'Switchboard', 'Bus', 'Transformer', 'Generator',
    'Cable', 'Breaker', 'Load', 'Motor', 'Relay', 'ProtectionDevice',
    'Conduit', 'Tray', 'Equipment', 'Annotation',
    
    # AI Agent
    'AICopilot', 'EngineeringIntentProcessor',
    
    # Translation Engine
    'TranslationEngine',
    
    # Connectors
    'AutoCADConnector', 'RevitConnector', 'ETAPConnector',
    
    # MCP Server
    'mcp_server', 'get_mcp_app'
]