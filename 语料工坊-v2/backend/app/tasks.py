import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TaskRecord:
    id: str
    status: str = "queued"
    stage: str = "queued"
    progress: float = 0
    message: str = ""
    transcript_id: str | None = None
    error: str | None = None
    subscribers: set[asyncio.Queue] = field(default_factory=set)


class TaskManager:
    def __init__(self) -> None:
        self.tasks: dict[str, TaskRecord] = {}

    def create(self) -> TaskRecord:
        task = TaskRecord(id=str(uuid.uuid4()))
        self.tasks[task.id] = task
        return task

    def get(self, task_id: str) -> TaskRecord | None:
        return self.tasks.get(task_id)

    async def update(self, task_id: str, **changes: Any) -> None:
        task = self.tasks[task_id]
        for key, value in changes.items():
            setattr(task, key, value)
        payload = self.to_dict(task)
        for queue in list(task.subscribers):
            await queue.put(payload)

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


task_manager = TaskManager()
