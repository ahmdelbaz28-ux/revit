"""
FireAI Live Sync Engine - Bidirectional synchronization
"""

import threading
import time
import logging
from datetime import datetime
from typing import Optional

from core.models import ChangeSource
from core.database import UniversalDataModel

logger = logging.getLogger(__name__)


class LiveSyncEngine(threading.Thread):
    """
    محرك المزامنة الحي: تتبع التغييرات والمزامنة ثنائية الاتجاه
    """
    
    def __init__(
        self,
        universal_model: UniversalDataModel,
        sync_interval: float = 2.0,
        conflict_strategy: str = 'SEMANTIC_MERGE'
    ):
        super().__init__(daemon=True)
        self.universal_model = universal_model
        self.sync_interval = sync_interval
        self.conflict_strategy = conflict_strategy
        self.is_running = False
        self.sync_count = 0
        
        logger.info(f"Live Sync Engine initialized (interval={sync_interval}s, strategy={conflict_strategy})")
    
    def start_sync(self):
        """بدء المزامنة"""
        self.is_running = True
        self.start()
        logger.info("Live Sync started")
    
    def stop_sync(self):
        """إيقاف المزامنة"""
        self.is_running = False
        logger.info("Live Sync stopped")
    
    def run(self):
        """الحلقة الرئيسية للمزامنة"""
        logger.info("Sync loop started")
        
        while self.is_running:
            try:
                self._perform_sync_cycle()
                time.sleep(self.sync_interval)
            except Exception as e:
                logger.error(f"Error in sync loop: {e}")
    
    def _perform_sync_cycle(self):
        """تنفيذ دورة مزامنة كاملة"""
        # Phase 1: Detect conflicts
        conflicts = self.universal_model.detect_conflicts()
        if conflicts:
            logger.warning(f"Detected {len(conflicts)} conflicts")
            for conflict in conflicts:
                self.universal_model.resolve_conflict(conflict, self.conflict_strategy)
        
        # Phase 2: Get pending changes
        autocad_pending = self.universal_model.get_pending_changes(ChangeSource.AUTOCAD)
        revit_pending = self.universal_model.get_pending_changes(ChangeSource.REVIT)
        
        if autocad_pending:
            logger.debug(f"AutoCAD→Revit: {len(autocad_pending)} changes pending")
            # In real implementation: call Revit adapter to apply changes
        
        if revit_pending:
            logger.debug(f"Revit→AutoCAD: {len(revit_pending)} changes pending")
            # In real implementation: call AutoCAD adapter to apply changes
        
        # Phase 3: Clear pending after sync
        if autocad_pending or revit_pending:
            self.universal_model.last_sync_timestamp = datetime.now()
            self.sync_count += 1
            logger.info(f"Sync cycle #{self.sync_count} completed")
    
    def get_status(self) -> dict:
        """الحصول على حالة المزامنة"""
        return {
            'is_running': self.is_running,
            'sync_count': self.sync_count,
            'last_sync': self.universal_model.last_sync_timestamp.isoformat() if self.universal_model.last_sync_timestamp else None,
            'pending_autocad': len(self.universal_model.pending_changes.get('autocad', [])),
            'pending_revit': len(self.universal_model.pending_changes.get('revit', []))
        }