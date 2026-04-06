"""
Abstract STT (Speech-to-Text) interface.

Allows swapping between different STT providers without changing pipeline code.
"""
from abc import ABC, abstractmethod
from typing import AsyncGenerator


class STTProvider(ABC):
    """Abstract base class for STT providers."""
    
    @abstractmethod
    async def transcribe_batch(self, audio_buffer: bytes) -> str:
        """
        Batch transcription - wait for complete audio before returning.
        
        Args:
            audio_buffer: Complete audio data (WebM, PCM, etc.)
        
        Returns:
            Complete transcript text
        """
        pass
    
    @abstractmethod
    async def transcribe_stream(
        self,
        audio_stream: AsyncGenerator[bytes, None]
    ) -> AsyncGenerator[str, None]:
        """
        Streaming transcription - yield partial transcripts as audio arrives.
        
        Args:
            audio_stream: Async generator yielding audio chunks
        
        Yields:
            Partial transcript strings (final results only)
        """
        pass
    
    @abstractmethod
    async def aclose(self) -> None:
        """Clean up resources (connection pools, etc.)."""
        pass
