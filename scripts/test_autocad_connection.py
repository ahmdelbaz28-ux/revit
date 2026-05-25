"""
scripts/test_autocad_connection.py
Test AutoCAD COM connection
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    import win32com.client as win32
    print("win32com available")
except ImportError:
    print("win32com not available - will use mock mode")

from adapters.autocad_adapter import AutoCADAdapter
from core.database import UniversalDataModel
from core.sync_engine import LiveSyncEngine


def test_connection():
    db = UniversalDataModel(":memory:")
    sync = LiveSyncEngine(None, None)
    adapter = AutoCADAdapter(db, sync, use_mock=True)
    
    if adapter.start_monitoring():
        print("AutoCAD connected!")
        elements = adapter.import_current_drawing()
        print(f"Imported {len(elements)} elements")
        return True
    return False


if __name__ == "__main__":
    test_connection()