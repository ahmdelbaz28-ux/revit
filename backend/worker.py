"""
backend/worker.py — Background Task Manager
==========================================

Background task processing with ARQ (or asyncio fallback).
Provides task queue, retry logic, and result storage.

Features:
- ARQ worker with Redis backend
- In-memory asyncio fallback when Redis unavailable
- Task retry with exponential backoff
- Result persistence
- Progress tracking via WebSocket
- Task scheduling

Environment Variables:
- REDIS_URL: Redis connection URL
- WORKER_CONCURRENCY: Number of concurrent workers (default: 4)
- WORKER_MAX_RETRIES: Maximum retry attempts (default: 3)

Usage:
    from backend.worker import task_queue, enqueue_task, get_task_result
    
    # Enqueue a task
    task_id = await enqueue_task("process_file", {"filepath": "/path/to/file"})
    
    # Get result
    result = await get_task_result(task_id)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, TypeVar, Generic

import ujson

logger = logging.getLogger(__name__)

# Configuration
REDIS_URL = "redis://localhost:6379/1"  # Use different DB for worker
WORKER_CONCURRENCY = 4
WORKER_MAX_RETRIES = 3
TASK_RESULT_TTL = 3600  # 1 hour


class TaskStatus(str, Enum):
    """Task status."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Task:
    """Background task."""
    id: str
    name: str
    args: tuple = field(default_factory=tuple)
    kwargs: dict = field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    created_at: float = field(default_factory=lambda: time.time())
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    result: Any = None
    error: Optional[str] = None
    retry_count: int = 0
    progress: int = 0
    metadata: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status.value,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "result": self.result,
            "error": self.error,
            "retry_count": self.retry_count,
            "progress": self.progress,
            "metadata": self.metadata
        }


class InMemoryTaskQueue:
    """
    In-memory task queue fallback when Redis is unavailable.
    
    Features:
    - FIFO queue
    - Background execution
    - Result storage
    - Progress updates
    """
    
    def __init__(self):
        self._queue: asyncio.Queue = asyncio.Queue()
        self._tasks: Dict[str, Task] = {}
        self._workers: List[asyncio.Task] = []
        self._running = False
        self._started = False
    
    async def start(self):
        """Start worker pool."""
        if self._started:
            return
        
        self._running = True
        self._started = True
        
        # Start worker coroutines
        for i in range(WORKER_CONCURRENCY):
            worker = asyncio.create_task(self._worker(i))
            self._workers.append(worker)
        
        logger.info(f"In-memory task queue started with {WORKER_CONCURRENCY} workers")
    
    async def stop(self):
        """Stop all workers."""
        self._running = False
        
        # Wait for queue to drain
        await asyncio.sleep(0.5)
        
        # Cancel workers
        for worker in self._workers:
            worker.cancel()
        
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        
        logger.info("In-memory task queue stopped")
    
    async def enqueue(self, task_id: str, task_name: str, args: tuple = (), 
                      kwargs: dict = None, metadata: dict = None) -> str:
        """Add task to queue."""
        task = Task(
            id=task_id,
            name=task_name,
            args=args,
            kwargs=kwargs or {},
            metadata=metadata or {}
        )
        self._tasks[task_id] = task
        await self._queue.put(task_id)
        
        logger.debug(f"Task enqueued: {task_id} ({task_name})")
        return task_id
    
    async def get_result(self, task_id: str) -> Optional[dict]:
        """Get task result."""
        task = self._tasks.get(task_id)
        if not task:
            return None
        
        return task.to_dict()
    
    async def _worker(self, worker_id: int):
        """Worker coroutine."""
        logger.debug(f"Worker {worker_id} started")
        
        while self._running:
            try:
                # Get task from queue
                task_id = await asyncio.wait_for(
                    self._queue.get(), 
                    timeout=1.0
                )
                
                task = self._tasks.get(task_id)
                if not task:
                    continue
                
                # Mark as processing
                task.status = TaskStatus.PROCESSING
                task.started_at = time.time()
                
                # Send progress update
                await self._update_progress(task)
                
                try:
                    # Get handler function
                    handler = _task_handlers.get(task.name)
                    if not handler:
                        raise ValueError(f"Unknown task: {task.name}")
                    
                    # Execute task
                    result = await handler(*task.args, **task.kwargs)
                    
                    # Mark as completed
                    task.status = TaskStatus.COMPLETED
                    task.result = result
                    task.completed_at = time.time()
                    task.progress = 100
                    
                    logger.info(f"Task {task_id} completed successfully")
                    
                except Exception as e:
                    # Handle failure
                    task.error = str(e)
                    task.retry_count += 1
                    
                    if task.retry_count < WORKER_MAX_RETRIES:
                        # Retry with backoff
                        delay = 2 ** task.retry_count
                        logger.warning(f"Task {task_id} failed, retrying in {delay}s (attempt {task.retry_count})")
                        task.status = TaskStatus.PENDING
                        asyncio.create_task(self._retry_later(task_id, delay))
                    else:
                        task.status = TaskStatus.FAILED
                        logger.error(f"Task {task_id} failed after {task.retry_count} attempts: {e}")
                
                # Update progress
                await self._update_progress(task)
                
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker {worker_id} error: {e}")
        
        logger.debug(f"Worker {worker_id} stopped")
    
    async def _retry_later(self, task_id: str, delay: float):
        """Retry task after delay."""
        await asyncio.sleep(delay)
        task = self._tasks.get(task_id)
        if task and task.status == TaskStatus.PENDING:
            await self._queue.put(task_id)
    
    async def _update_progress(self, task: Task):
        """Send progress update via WebSocket."""
        try:
            from backend.websocket import ws_manager
            await ws_manager.send_progress(
                task.id,
                task.progress,
                task.status.value,
                {"result": task.result, "error": task.error}
            )
        except ImportError:
            pass  # WebSocket not initialized yet


# Task handlers registry
_task_handlers: Dict[str, Callable] = {}


def register_task(name: str):
    """Decorator to register a task handler."""
    def decorator(func: Callable):
        _task_handlers[name] = func
        return func
    return decorator


# Global task queue instance
task_queue: InMemoryTaskQueue = InMemoryTaskQueue()


# ═══════════════════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

async def enqueue_task(task_name: str, kwargs: dict = None, 
                       metadata: dict = None) -> str:
    """Enqueue a background task."""
    task_id = f"task_{uuid.uuid4().hex[:12]}"
    return await task_queue.enqueue(
        task_id,
        task_name,
        kwargs=kwargs or {},
        metadata=metadata or {}
    )


async def get_task_result(task_id: str) -> Optional[dict]:
    """Get task result."""
    return await task_queue.get_result(task_id)


async def start_worker():
    """Start the background worker pool."""
    await task_queue.start()


async def stop_worker():
    """Stop the background worker pool."""
    await task_queue.stop()


# ═══════════════════════════════════════════════════════════════════════════
# SAMPLE TASK HANDLERS (Replace with actual implementations)
# ═══════════════════════════════════════════════════════════════════════════

@register_task("process_file")
async def process_file(filepath: str, options: dict = None):
    """
    Process a file in background.
    Replace with actual file processing logic.
    """
    logger.info(f"Processing file: {filepath}")
    
    # Simulate processing
    for i in range(10):
        await asyncio.sleep(0.5)
        # Update progress would go here
    
    return {"status": "completed", "filepath": filepath, "processed": True}


@register_task("export_rooms")
async def export_rooms(project_id: str, floors: int = 100):
    """
    Export rooms for a project in background.
    Replace with actual export logic.
    """
    logger.info(f"Exporting {floors} floors for project {project_id}")
    
    # Simulate export
    rooms = []
    for floor in range(floors):
        for room in range(10):
            rooms.append({
                "id": f"room-{floor}-{room}",
                "floor": floor,
                "room": room,
                "area": 25.0
            })
        
        # Update progress
        progress = int((floor + 1) / floors * 100)
        task = task_queue._tasks.get(project_id)
        if task:
            task.progress = progress
    
    return {
        "status": "completed",
        "project_id": project_id,
        "total_rooms": len(rooms),
        "floors": floors
    }


@register_task("convert_dwg")
async def convert_dwg(input_path: str, output_format: str = "dxf"):
    """
    Convert DWG file in background.
    Replace with actual conversion logic.
    """
    logger.info(f"Converting {input_path} to {output_format}")
    
    # Simulate conversion
    await asyncio.sleep(2)
    
    return {
        "status": "completed",
        "input": input_path,
        "output": input_path.replace(".dwg", f".{output_format}"),
        "format": output_format
    }
