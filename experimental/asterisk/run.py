"""Separate AudioSocket process. The main web application never imports this."""
import asyncio
import logging
import socket
from uuid import UUID as CallUUID

import httpx
from .audio import EnergyUtteranceDetector
from .client import AudioConverter, ExistingPipeline
from .config import TelephonyConfig
from .protocol import UUID, PCM_8K, DTMF, HANGUP, ERROR, ProtocolError, read_frame, write_frame


LOG = logging.getLogger('telephony')


class AudioSocketCall:
    def __init__(self, reader, writer, pipeline, config):
        self.reader, self.writer, self.pipeline, self.config = reader, writer, pipeline, config
        self.detector = EnergyUtteranceDetector(threshold=config.vad_threshold)
        self.queue = asyncio.Queue(maxsize=2)
        self.generation = 0
        self.pcm, self.offset = b'', 0
        self.closed = False
        self.output_task = None
        self.notifications = set()
        self.state, self.last_answer = None, None

    def barge_in(self):
        self.generation += 1
        audible = bool(self.pcm) or (self.output_task is not None and not self.output_task.done())
        self.pcm, self.offset = b'', 0
        if self.output_task and not self.output_task.done():
            self.output_task.cancel()  # Only TTS/decoding; never cancel chat here.
        if audible and self.last_answer:
            task = asyncio.create_task(self.pipeline.interrupt(
                self.last_answer['conversation_id'], self.last_answer['turn_id']))
            self.notifications.add(task)
            task.add_done_callback(self.notifications.discard)

    async def receive(self):
        while not self.closed:
            frame = await read_frame(self.reader, timeout=self.config.idle_timeout)
            if frame is None or frame.kind == HANGUP:
                return
            if frame.kind == ERROR:
                raise ProtocolError('AudioSocket peer error')
            if frame.kind == DTMF:
                continue  # Unsupported control input must not confirm an action.
            if frame.kind != PCM_8K:
                raise ProtocolError('Unexpected AudioSocket frame after UUID')
            for event in self.detector.feed(frame.payload):
                if event.kind == 'speech_start':
                    self.barge_in()
                elif event.kind == 'utterance':
                    # Preserve order. Never silently replace an earlier user turn.
                    self.queue.put_nowait((self.generation, event.pcm))
                elif event.kind == 'discarded':
                    LOG.info('utterance discarded: %s', event.reason)

    async def send(self):
        # AudioSocket media must be paced. Silence keeps the Asterisk channel
        # alive while the existing STT/agent/TTS pipeline handles a final turn.
        loop = asyncio.get_running_loop()
        deadline = loop.time()
        while not self.closed:
            chunk = self.pcm[self.offset:self.offset+320]
            if chunk:
                self.offset += len(chunk)
                if self.offset >= len(self.pcm):
                    self.pcm, self.offset = b'', 0
            await write_frame(self.writer, PCM_8K, chunk.ljust(320, b'\0'), timeout=self.config.io_timeout)
            deadline = max(deadline + 0.02, loop.time() + 0.001)
            await asyncio.sleep(max(0, deadline-loop.time()))

    async def process(self):
        self.state = await self.pipeline.create(self.config.language)
        while not self.closed:
            token, pcm = await self.queue.get()
            try:
                answer = await self.pipeline.turn(self.state, pcm)
                self.last_answer = answer
                if token != self.generation:
                    continue  # A later final utterance is waiting; omit old audio.
                self.output_task = asyncio.create_task(self.pipeline.speech(answer))
                try:
                    audio = await self.output_task
                except asyncio.CancelledError:
                    if self.closed or asyncio.current_task().cancelling():
                        raise
                    continue
                finally:
                    self.output_task = None
                if token == self.generation and not self.closed:
                    self.pcm, self.offset = audio, 0
            finally:
                self.queue.task_done()

    async def run(self):
        first = await read_frame(self.reader, timeout=self.config.io_timeout)
        if first is None or first.kind != UUID:
            raise ProtocolError('AudioSocket UUID required first')
        CallUUID(bytes=first.payload)  # Correlation only, never a customer identity.
        connection = self.writer.get_extra_info('socket')
        if connection:
            connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        tasks = [asyncio.create_task(fn()) for fn in (self.receive, self.send, self.process)]
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        finally:
            self.closed = True
            self.pcm = b''
            for task in [*tasks, *self.notifications]:
                task.cancel()
            await asyncio.gather(*tasks, *self.notifications, return_exceptions=True)


class AudioSocketBridge:
    def __init__(self, pipeline, config):
        self.pipeline, self.config = pipeline, config
        self.active = set()

    async def handle(self, reader, writer):
        task = asyncio.current_task()
        if len(self.active) >= self.config.max_calls:
            writer.close()
            await writer.wait_closed()
            return
        self.active.add(task)
        try:
            async with asyncio.timeout(self.config.call_timeout):
                await AudioSocketCall(reader, writer, self.pipeline, self.config).run()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            LOG.warning('call unavailable — closed (%s)', type(exc).__name__)
        finally:
            self.active.discard(task)
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass

    async def close(self):
        tasks = list(self.active)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def run(config: TelephonyConfig):
    if not config.enabled:
        return
    converter = AudioConverter(config.ffmpeg)
    async with httpx.AsyncClient(base_url=config.backend_url, timeout=config.api_timeout) as client:
        pipeline = ExistingPipeline(client, converter)
        await pipeline.preflight()  # Only this independent process waits.
        bridge = AudioSocketBridge(pipeline, config)
        server = await asyncio.start_server(bridge.handle, config.host, config.port, limit=8192)
        LOG.info('experimental AudioSocket ready on %s:%s', config.host, config.port)
        try:
            async with server:
                await server.serve_forever()
        finally:
            await bridge.close()
