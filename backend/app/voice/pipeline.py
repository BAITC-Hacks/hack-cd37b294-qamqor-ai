"""Final-utterance adapter. Text, browser audio and optional Pipecat use the same service."""
from app.state.models import ChatRequest


class FinalUtteranceAdapter:
    def __init__(self, conversations): self.conversations=conversations

    async def process(self, conversation_id, turn_id, text, *, final, **kwargs):
        if not final: return None
        return await self.conversations.chat(ChatRequest(conversation_id=conversation_id,turn_id=turn_id,text=text,input_mode='voice',**kwargs))


class PipecatAdapter(FinalUtteranceAdapter):
    """Optional Pipecat bridge; imports only when a Pipecat deployment uses it."""
    async def process_transcription(self, frame, conversation_id, turn_id):
        from pipecat.frames.frames import TranscriptionFrame, InterimTranscriptionFrame
        if isinstance(frame,InterimTranscriptionFrame): return None
        if not isinstance(frame,TranscriptionFrame): return None
        return await self.process(conversation_id,turn_id,frame.text,final=True)
