import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


TERMINAL_STATUSES = {"completed", "failed"}
MAX_TASKS = 200
TASK_RETENTION_SECONDS = 24 * 60 * 60


@dataclass
class TaskRecord:
    id: str
    status: str = "queued"
    stage: str = "queued"
    progress: float = 0
    message: str = ""
    transcript_id: str | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    subscribers: set[asyncio.Queue] = field(default_factory=set)


class TaskManager:
    def __init__(self) -> None:
        self.tasks: dict[str, TaskRecord] = {}

    def create(self) -> TaskRecord:
        self.cleanup()
        task = TaskRecord(id=str(uuid.uuid4()))
        self.tasks[task.id] = task
        return task

    def get(self, task_id: str) -> TaskRecord | None:
        return self.tasks.get(task_id)

    async def update(self, task_id: str, **changes: Any) -> None:
        task = self.tasks[task_id]
        for key, value in changes.items():
            setattr(task, key, value)
        task.updated_at = time.time()
        payload = self.to_dict(task)
        for queue in list(task.subscribers):
            await queue.put(payload)
        self.cleanup()

    def to_dict(self, task: TaskRecord) -> dict[str, Any]:
        return {
            "id": task.id,
            "status": task.status,
            "stage": task.stage,
            "progress": task.progress,
            "message": task.message,
            "transcript_id": task.transcript_id,
            "error": task.error,
        }

    async def subscribe(self, task_id: str) -> asyncio.Queue:
        task = self.tasks[task_id]
        queue: asyncio.Queue = asyncio.Queue()
        task.subscribers.add(queue)
        await queue.put(self.to_dict(task))
        return queue

    def unsubscribe(self, task_id: str, queue: asyncio.Queue) -> None:
        task = self.tasks.get(task_id)
        if task:
            task.subscribers.discard(queue)

    def cleanup(self) -> None:
        now = time.time()
        for task_id, task in list(self.tasks.items()):
            if task.subscribers:
                continue
            if task.status in TERMINAL_STATUSES and now - task.updated_at > TASK_RETENTION_SECONDS:
                self.tasks.pop(task_id, None)

        if len(self.tasks) <= MAX_TASKS:
            return
        removable = sorted(
            (
                task
                for task in self.tasks.values()
                if not task.subscribers and task.status in TERMINAL_STATUSES
            ),
            key=lambda task: task.updated_at,
        )
        for task in removable[: max(0, len(self.tasks) - MAX_TASKS)]:
            self.tasks.pop(task.id, None)


task_manager = TaskManager()
