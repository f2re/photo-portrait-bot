"""
User processing locks to prevent concurrent image processing
"""
import asyncio
from typing import Dict, Set
from contextlib import asynccontextmanager


class UserProcessingLock:
    """
    Manages locks for user image processing to prevent concurrent requests
    """
    def __init__(self):
        self._locks: Dict[int, asyncio.Lock] = {}
        self._processing: Set[int] = set()
        self._main_lock = asyncio.Lock()

    @asynccontextmanager
    async def acquire(self, user_id: int):
        """
        Acquire lock for user image processing

        Args:
            user_id: Telegram user ID

        Raises:
            RuntimeError: If user already has a processing request
        """
        async with self._main_lock:
            # Check if user is already processing
            if user_id in self._processing:
                raise RuntimeError("Already processing image for this user")

            # Get or create lock for this user
            if user_id not in self._locks:
                self._locks[user_id] = asyncio.Lock()

            lock = self._locks[user_id]
            self._processing.add(user_id)

        try:
            async with lock:
                yield
        finally:
            async with self._main_lock:
                self._processing.discard(user_id)
                # Clean up lock if no longer needed
                if user_id in self._locks and user_id not in self._processing:
                    # Keep the lock object for a bit to avoid recreating it
                    # Only clean up if it's unlocked
                    if not self._locks[user_id].locked():
                        del self._locks[user_id]

    def is_processing(self, user_id: int) -> bool:
        """Check if user is currently processing an image"""
        return user_id in self._processing


# Global instance
user_processing_lock = UserProcessingLock()
