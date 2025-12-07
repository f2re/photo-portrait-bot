"""
Yandex Metrika integration service for offline conversions tracking.

This service provides:
1. Event tracking to database (always works, even without Metrika configured)
2. Automatic upload of events to Yandex Metrika via Offline Conversions API
3. Retry mechanism with exponential backoff
4. Comprehensive error handling and logging

API Documentation:
https://yandex.ru/dev/metrika/doc/api2/management/offline_conversions/offline_conversions.html
"""

import asyncio
import csv
import io
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

import aiohttp
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.models import UTMEvent, User


logger = logging.getLogger(__name__)


class YandexMetrikaService:
    """Service for tracking events and uploading to Yandex Metrika"""

    def __init__(self):
        self.counter_id = settings.YANDEX_METRIKA_COUNTER_ID
        self.token = settings.YANDEX_METRIKA_TOKEN
        self.is_enabled = settings.is_metrika_enabled

        if self.is_enabled:
            self.api_url = (
                f"https://api-metrika.yandex.net/management/v1/"
                f"counter/{self.counter_id}/offline_conversions/upload"
            )
            logger.info(
                f"Yandex Metrika enabled. Counter ID: {self.counter_id}, "
                f"Upload interval: {settings.METRIKA_UPLOAD_INTERVAL}s"
            )
        else:
            logger.info(
                "Yandex Metrika is disabled. Events will be stored in database only. "
                "To enable, set YANDEX_METRIKA_COUNTER_ID and YANDEX_METRIKA_TOKEN in .env"
            )

    async def track_event(
        self,
        session: AsyncSession,
        user_id: int,
        event_type: str,
        event_value: Optional[float] = None,
        currency: str = "RUB",
        event_data: Optional[Dict[str, Any]] = None
    ) -> Optional[UTMEvent]:
        """
        Track an event to database. Will be uploaded to Metrika later.

        Args:
            session: Database session
            user_id: User ID (database ID, not telegram_id)
            event_type: Event type (start, first_image, purchase, etc.)
            event_value: Optional monetary value for conversion
            currency: Currency code (default: RUB)
            event_data: Optional additional data as JSON

        Returns:
            Created UTMEvent object or None if failed
        """
        try:
            # Get user's metrika_client_id
            user = await session.get(User, user_id)
            if not user:
                logger.error(f"User {user_id} not found when tracking event {event_type}")
                return None

            if not user.metrika_client_id:
                logger.warning(
                    f"User {user_id} has no metrika_client_id. "
                    f"Event {event_type} will be tracked without Metrika integration."
                )

            # Create event record
            event = UTMEvent(
                user_id=user_id,
                event_type=event_type,
                metrika_client_id=user.metrika_client_id,
                event_value=event_value,
                currency=currency,
                event_data=event_data or {},
                sent_to_metrika=False,
                created_at=datetime.utcnow()
            )

            session.add(event)
            await session.commit()
            await session.refresh(event)

            logger.info(
                f"Event tracked: {event_type} for user {user_id} "
                f"(metrika_client_id: {user.metrika_client_id or 'N/A'})"
            )

            return event

        except Exception as e:
            logger.error(f"Error tracking event {event_type} for user {user_id}: {e}", exc_info=True)
            await session.rollback()
            return None

    async def upload_pending_events(self, session: AsyncSession) -> bool:
        """
        Upload all pending events to Yandex Metrika.

        Args:
            session: Database session

        Returns:
            True if successfully uploaded or Metrika is disabled, False on error
        """
        if not self.is_enabled:
            logger.debug("Metrika is disabled. Skipping event upload.")
            return True

        try:
            # Get all unsent events with metrika_client_id
            stmt = (
                select(UTMEvent)
                .where(UTMEvent.sent_to_metrika == False)
                .where(UTMEvent.metrika_client_id.isnot(None))
                .order_by(UTMEvent.created_at)
            )
            result = await session.execute(stmt)
            events = result.scalars().all()

            if not events:
                logger.debug("No pending events to upload to Metrika")
                return True

            logger.info(f"Found {len(events)} pending events to upload to Metrika")

            # Separate events with and without price
            events_with_price = []
            events_without_price = []

            for event in events:
                # Get user's telegram_id for UserID (Telegram bots don't have ClientID from cookies)
                user = await session.get(User, event.user_id)
                if not user:
                    logger.warning(f"User {event.user_id} not found for event {event.id}, skipping")
                    continue

                conversion = {
                    "UserId": str(user.telegram_id),  # Use telegram_id as UserID
                    "Target": self._get_goal_name(event.event_type),
                    "DateTime": int(event.created_at.timestamp()),
                }

                # Add price for purchase events
                if event.event_value:
                    conversion["Price"] = float(event.event_value)
                    conversion["Currency"] = event.currency or "RUB"
                    events_with_price.append(conversion)
                else:
                    events_without_price.append(conversion)

            # Upload events in separate batches (with price and without)
            upload_id = None
            success = True

            if events_without_price:
                logger.info(f"Uploading {len(events_without_price)} events without price")
                upload_id = await self._upload_conversions(events_without_price)
                if not upload_id:
                    success = False

            if events_with_price:
                logger.info(f"Uploading {len(events_with_price)} events with price")
                upload_id_price = await self._upload_conversions(events_with_price)
                if not upload_id_price:
                    success = False
                else:
                    upload_id = upload_id_price  # Use last upload_id for tracking

            if success and upload_id:
                # Mark events as sent
                event_ids = [event.id for event in events]
                stmt = (
                    update(UTMEvent)
                    .where(UTMEvent.id.in_(event_ids))
                    .values(
                        sent_to_metrika=True,
                        sent_at=datetime.utcnow(),
                        metrika_upload_id=upload_id
                    )
                )
                await session.execute(stmt)
                await session.commit()

                logger.info(
                    f"Successfully uploaded {len(events)} events to Metrika "
                    f"({len(events_without_price)} without price, {len(events_with_price)} with price)"
                )
                return True
            else:
                logger.error("Failed to upload events to Metrika")
                return False

        except Exception as e:
            logger.error(f"Error uploading events to Metrika: {e}", exc_info=True)
            await session.rollback()
            return False

    def _get_goal_name(self, event_type: str) -> str:
        """
        Map event type to Metrika goal name.

        Args:
            event_type: Internal event type

        Returns:
            Metrika goal name
        """
        mapping = {
            "start": settings.METRIKA_GOAL_START,
            "first_image": settings.METRIKA_GOAL_FIRST_IMAGE,
            "purchase": settings.METRIKA_GOAL_PURCHASE,
        }
        return mapping.get(event_type, event_type)

    async def _upload_conversions(
        self,
        conversions: List[Dict[str, Any]],
        comment: str = "Auto upload from bot"
    ) -> Optional[str]:
        """
        Upload conversions to Yandex Metrika API.

        Args:
            conversions: List of conversion dicts
            comment: Upload comment

        Returns:
            Upload ID from Metrika or None if failed
        """
        if not conversions:
            return None

        try:
            # Create CSV content
            csv_content = self._create_csv(conversions)

            # Upload to Metrika with retry
            max_retries = 3
            retry_delay = 2  # seconds

            for attempt in range(max_retries):
                try:
                    async with aiohttp.ClientSession() as client_session:
                        headers = {
                            "Authorization": f"OAuth {self.token}"
                        }

                        data = aiohttp.FormData()
                        data.add_field(
                            'file',
                            csv_content,
                            filename='conversions.csv',
                            content_type='text/csv'
                        )

                        params = {
                            "client_id_type": "USER_ID",  # Use USER_ID for Telegram bot (not CLIENT_ID from cookies)
                            "comment": comment
                        }

                        async with client_session.post(
                            self.api_url,
                            headers=headers,
                            data=data,
                            params=params,
                            timeout=aiohttp.ClientTimeout(total=30)
                        ) as response:
                            if response.status == 200:
                                result = await response.json()
                                upload_id = result.get('uploading', {}).get('id')
                                logger.info(
                                    f"Conversions uploaded successfully. "
                                    f"Upload ID: {upload_id}, rows: {len(conversions)}"
                                )
                                return str(upload_id) if upload_id else None
                            else:
                                error_text = await response.text()
                                logger.error(
                                    f"Metrika API error (attempt {attempt + 1}/{max_retries}): "
                                    f"{response.status} - {error_text}"
                                )

                                # Don't retry on client errors (4xx)
                                if 400 <= response.status < 500:
                                    return None

                except asyncio.TimeoutError:
                    logger.warning(
                        f"Metrika API timeout (attempt {attempt + 1}/{max_retries})"
                    )
                except aiohttp.ClientError as e:
                    logger.warning(
                        f"Metrika API connection error (attempt {attempt + 1}/{max_retries}): {e}"
                    )

                # Wait before retry (exponential backoff)
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (2 ** attempt))

            logger.error(f"Failed to upload conversions after {max_retries} attempts")
            return None

        except Exception as e:
            logger.error(f"Unexpected error uploading conversions: {e}", exc_info=True)
            return None

    def _create_csv(self, conversions: List[Dict[str, Any]]) -> str:
        """
        Create CSV file content from conversions.

        Args:
            conversions: List of conversion dicts

        Returns:
            CSV content as string
        """
        output = io.StringIO()

        # Determine fieldnames based on whether conversions have prices
        # All conversions in a batch should be either with or without price
        has_price = any('Price' in conv for conv in conversions)

        if has_price:
            fieldnames = ["UserId", "Target", "DateTime", "Price", "Currency"]
        else:
            fieldnames = ["UserId", "Target", "DateTime"]

        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(conversions)

        csv_content = output.getvalue()

        # Log the CSV content for debugging
        logger.debug(f"Generated CSV for Metrika upload ({len(conversions)} conversions):\n{csv_content}")

        return csv_content

    async def get_upload_status(
        self,
        upload_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get status of a specific upload from Metrika API.

        Args:
            upload_id: Upload ID from Metrika

        Returns:
            Upload status dict or None if failed
        """
        if not self.is_enabled:
            return None

        try:
            status_url = (
                f"https://api-metrika.yandex.net/management/v1/"
                f"counter/{self.counter_id}/offline_conversions/upload/{upload_id}"
            )

            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": f"OAuth {self.token}"
                }

                async with session.get(
                    status_url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        error_text = await response.text()
                        logger.error(
                            f"Failed to get upload status for {upload_id}: "
                            f"{response.status} - {error_text}"
                        )
                        return None

        except Exception as e:
            logger.error(f"Error getting upload status for {upload_id}: {e}", exc_info=True)
            return None


# Global service instance
metrika_service = YandexMetrikaService()


async def periodic_metrika_upload(get_db_session):
    """
    Background task to periodically upload events to Yandex Metrika.

    Args:
        get_db_session: Async context manager for getting database session
    """
    logger.info(
        f"Starting periodic Metrika upload task. "
        f"Interval: {settings.METRIKA_UPLOAD_INTERVAL}s"
    )

    while True:
        try:
            await asyncio.sleep(settings.METRIKA_UPLOAD_INTERVAL)

            async with get_db_session() as session:
                await metrika_service.upload_pending_events(session)

        except asyncio.CancelledError:
            logger.info("Periodic Metrika upload task cancelled")
            break
        except Exception as e:
            logger.error(f"Error in periodic Metrika upload: {e}", exc_info=True)
            # Continue running even if upload fails
            await asyncio.sleep(60)  # Wait 1 minute before retrying
