import asyncio
import logging


class Tracer:
    def __init__(self, repository):
        self.repository = repository
        self.queue = asyncio.Queue(maxsize=512)
        self.recent = {}
        self.worker = None
        self.dropped = 0

    def start(self):
        self.worker = asyncio.create_task(self.run())

    def emit(self, event):
        self.recent[event['event_id']] = event
        if len(self.recent) > 500:
            self.recent.pop(next(iter(self.recent)))
        try:
            self.queue.put_nowait(event)
        except asyncio.QueueFull:
            self.dropped += 1

    async def run(self):
        while True:
            event = await self.queue.get()
            try:
                await asyncio.to_thread(self.repository.save_event, event)
            except Exception:
                logging.exception('Trace persistence failed')
            finally:
                self.queue.task_done()

    def events(self, conversation_id=None):
        events = {e['event_id']: e for e in self.repository.events(conversation_id)}
        events.update({k:v for k,v in self.recent.items() if not conversation_id or v['conversation_id'] == conversation_id})
        return sorted(events.values(), key=lambda e:e['timestamp'], reverse=True)[:100]

    async def close(self):
        await self.queue.join()
        if self.worker:
            self.worker.cancel()
            try:
                await self.worker
            except asyncio.CancelledError:
                pass
