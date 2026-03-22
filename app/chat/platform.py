"""Chat platform abstraction — pluggable interface for Telegram, WhatsApp, etc."""

from abc import ABC, abstractmethod
from typing import Optional


class ChatPlatform(ABC):
    """Abstract chat platform interface."""

    @abstractmethod
    async def send_message(
        self,
        chat_id: int | str,
        text: str,
        reply_markup=None,
        parse_mode: Optional[str] = None,
    ) -> None:
        """Send a text message."""

    @abstractmethod
    async def send_photo(
        self,
        chat_id: int | str,
        photo,
        caption: Optional[str] = None,
    ) -> None:
        """Send a photo."""

    @abstractmethod
    async def send_document(
        self,
        chat_id: int | str,
        document,
        caption: Optional[str] = None,
    ) -> None:
        """Send a document/file."""

    @abstractmethod
    async def start(self) -> None:
        """Start the chat platform (polling/webhook)."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop the chat platform."""
