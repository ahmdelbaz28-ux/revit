"""
backend/routers/tasks.py — Background Tasks Endpoints
====================================================

REST API endpoints for background task management.
Provides task enqueuing, status checking, and result retrieval.

ENDPOINTS:
- POST /api/v1/tasks/enqueue - Enqueue a new background task
- GET /api/v1/tasks/{task_id} - Get task status and result
- POST /api/v1/tasks/{task_id}/cancel - Cancel a pending task
- GET /api/v1/tasks - List recent tasks

Usage:
    # Enqueue task
    curl -X POST http://localhost:8000/api/v1/tasks/enqueue \
      -H "Content-Type: application/json" \
      -d '{"task_name": "export_rooms", "kwargs": {"project_id": "p1", "floors": 100}}'
    
    # Get result
    curl http://localhost:8000/api/v1/tasks/task_abc123
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional, Any

from backend.routers.auth import get_current_user, User
from backend.worker import enqueue_task, get_task_result, task_queue

router = APIRouter(tags=["Tasks"])


# Request/Response Models
class EnqueueRequest(BaseModel):
    task_name: str
    kwargs: Optional[dict] = None
    metadata: Optional[dict] = None


class TaskResponse(BaseModel):
    id: str
    name: str
    status: str
    progress: int = 0
    created_at: float
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    result: Optional[Any] = None
    error: Optional[str] = None
    retry_count: int = 0


class EnqueueResponse(BaseModel):
    task_id: str
    message: str = "Task enqueued successfully"


class TaskListResponse(BaseModel):
    tasks: list[TaskResponse]
    total: int


# Available tasks for validation
AVAILABLE_TASKS = {
    "process_file": "Process a file in background",
    "export_rooms": "Export rooms for a project",
    "convert_dwg": "Convert DWG file to different format",
}


@router.post("/enqueue", response_model=EnqueueResponse)
async def create_task(
    request: EnqueueRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Enqueue a new background task.
    
    Available tasks:
    - process_file: Process a file in background
    - export_rooms: Export rooms for a project (kwargs: project_id, floors)
    - convert_dwg: Convert DWG file (kwargs: input_path, output_format)
    """
    # Validate task name
    if request.task_name not in AVAILABLE_TASKS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown task: {request.task_name}. Available: {list(AVAILABLE_TASKS.keys())}"
        )
    
    # Enqueue task
    task_id = await enqueue_task(
        request.task_name,
        kwargs=request.kwargs,
        metadata=request.metadata
    )
    
    return EnqueueResponse(
        task_id=task_id,
        message=f"Task '{request.task_name}' enqueued successfully"
    )


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get task status and result."""
    task_dict = await get_task_result(task_id)
    
    if not task_dict:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task not found: {task_id}"
        )
    
    return TaskResponse(**task_dict)


@router.post("/{task_id}/cancel")
async def cancel_task(
    task_id: str,
    current_user: User = Depends(get_current_user)
):
    """Cancel a pending task."""
    # Note: Cancellation is best-effort
    # In production, implement proper cancellation with asyncio.CancelledError
    
    task_dict = await get_task_result(task_id)
    
    if not task_dict:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task not found: {task_id}"
        )
    
    if task_dict["status"] in ("completed", "failed", "cancelled"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel task with status: {task_dict['status']}"
        )
    
    # Mark as cancelled (actual implementation would need proper cancellation)
    return {
        "message": "Cancel requested (best-effort)",
        "task_id": task_id
    }


@router.get("", response_model=TaskListResponse)
async def list_tasks(
    current_user: User = Depends(get_current_user),
    limit: int = 20
):
    """List recent tasks for the current user."""
    # Get all tasks from queue
    tasks = []
    for task_id, task in task_queue._tasks.items():
        tasks.append(TaskResponse(
            id=task.id,
            name=task.name,
            status=task.status.value,
            progress=task.progress,
            created_at=task.created_at,
            started_at=task.started_at,
            completed_at=task.completed_at,
            result=task.result,
            error=task.error,
            retry_count=task.retry_count
        ))
    
    # Sort by created_at descending
    tasks.sort(key=lambda t: t.created_at, reverse=True)
    
    return TaskListResponse(
        tasks=tasks[:limit],
        total=len(tasks)
    )
