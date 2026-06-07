import asyncio

class TaskManager:
    def __init__(self):
        self.user_tasks: dict[int, list[asyncio.Task]] = {}

    def start_task(self, user_id: int, coro) -> None:
        existing = [t for t in self.user_tasks.get(user_id, []) if not t.done()]
        self.user_tasks[user_id] = existing
        task = asyncio.create_task(coro)
        existing.append(task)

    def stop_tasks(self, user_id: int) -> None:
        tasks = self.user_tasks.pop(user_id, [])
        for task in tasks:
            if not task.done():
                task.cancel()

    def is_active(self, user_id: int) -> bool:
        return any(not t.done() for t in self.user_tasks.get(user_id, []))
