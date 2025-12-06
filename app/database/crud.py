from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import select, func, and_, update, desc, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import uuid

from .models import User, Package, Order, ProcessedImage, SupportTicket, SupportMessage, Admin, UTMEvent, ReferralReward


# ==================== USER OPERATIONS ====================

async def get_or_create_user(
    session: AsyncSession,
    telegram_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
    free_images_count: int = 3,
    utm_source: Optional[str] = None,
    utm_medium: Optional[str] = None,
    utm_campaign: Optional[str] = None,
    utm_content: Optional[str] = None,
    utm_term: Optional[str] = None
) -> User:
    """
    Get existing user or create new one with UTM tracking.

    Args:
        session: Database session
        telegram_id: Telegram user ID
        username: Telegram username
        first_name: User's first name
        free_images_count: Number of free images for new users
        utm_source: UTM source parameter
        utm_medium: UTM medium parameter
        utm_campaign: UTM campaign parameter
        utm_content: UTM content parameter
        utm_term: UTM term parameter

    Returns:
        User object
    """
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        # Generate unique metrika_client_id for new users
        metrika_client_id = str(uuid.uuid4())

        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            free_images_left=free_images_count,
            utm_source=utm_source,
            utm_medium=utm_medium,
            utm_campaign=utm_campaign,
            utm_content=utm_content,
            utm_term=utm_term,
            metrika_client_id=metrika_client_id
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
    else:
        # Update existing user's UTM if they don't have UTM data yet
        # AND new UTM data is provided
        needs_update = False

        if not user.utm_source and utm_source:
            user.utm_source = utm_source
            needs_update = True

        if not user.utm_medium and utm_medium:
            user.utm_medium = utm_medium
            needs_update = True

        if not user.utm_campaign and utm_campaign:
            user.utm_campaign = utm_campaign
            needs_update = True

        if not user.utm_content and utm_content:
            user.utm_content = utm_content
            needs_update = True

        if not user.utm_term and utm_term:
            user.utm_term = utm_term
            needs_update = True

        # Generate metrika_client_id if missing
        if not user.metrika_client_id:
            user.metrika_client_id = str(uuid.uuid4())
            needs_update = True

        if needs_update:
            await session.commit()
            await session.refresh(user)

    return user


async def get_user_balance(session: AsyncSession, telegram_id: int) -> dict:
    """Get user's balance (free + paid images)"""
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        return {"free": 0, "paid": 0, "total": 0}

    # Count paid images from successful orders
    paid_result = await session.execute(
        select(func.sum(Package.images_count))
        .join(Order, Order.package_id == Package.id)
        .where(and_(Order.user_id == user.id, Order.status == "paid"))
    )
    paid_total = paid_result.scalar() or 0

    # Count used paid images
    used_result = await session.execute(
        select(func.count(ProcessedImage.id))
        .where(and_(ProcessedImage.user_id == user.id, ProcessedImage.is_free == False))
    )
    used_paid = used_result.scalar() or 0

    paid_left = max(0, paid_total - used_paid)

    return {
        "free": user.free_images_left,
        "paid": paid_left,
        "total": user.free_images_left + paid_left
    }


async def decrease_balance(session: AsyncSession, telegram_id: int) -> bool:
    """Decrease user's balance (prioritize free images)"""
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        return False

    if user.free_images_left > 0:
        user.free_images_left -= 1
        await session.commit()
        return True

    # Check if user has paid images
    balance = await get_user_balance(session, telegram_id)
    if balance["paid"] > 0:
        return True

    return False


async def check_and_reserve_balance(session: AsyncSession, telegram_id: int) -> tuple[bool, bool]:
    """
    Atomically check and reserve balance for image processing with row-level locking
    This prevents race conditions when multiple requests come in simultaneously

    Args:
        session: Database session
        telegram_id: Telegram user ID

    Returns:
        tuple: (success: bool, is_free: bool)
            success: Whether balance was successfully reserved
            is_free: Whether a free image was used
    """
    # Use FOR UPDATE to lock the row and prevent concurrent modifications
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id).with_for_update()
    )
    user = result.scalar_one_or_none()

    if not user:
        return False, False

    # Try to use free image first
    if user.free_images_left > 0:
        user.free_images_left -= 1
        await session.commit()
        return True, True

    # Check if user has paid images available
    # Count paid images from successful orders
    paid_result = await session.execute(
        select(func.sum(Package.images_count))
        .join(Order, Order.package_id == Package.id)
        .where(and_(Order.user_id == user.id, Order.status == "paid"))
    )
    paid_total = paid_result.scalar() or 0

    # Count used paid images
    used_result = await session.execute(
        select(func.count(ProcessedImage.id))
        .where(and_(ProcessedImage.user_id == user.id, ProcessedImage.is_free == False))
    )
    used_paid = used_result.scalar() or 0

    paid_left = paid_total - used_paid

    if paid_left > 0:
        # User has paid images, don't decrease anything here
        # The ProcessedImage record will be created later to track usage
        await session.commit()  # Release the lock
        return True, False

    # No balance available
    await session.commit()  # Release the lock
    return False, False


async def rollback_balance(session: AsyncSession, telegram_id: int, is_free: bool):
    """
    Rollback balance reservation if processing failed

    Args:
        session: Database session
        telegram_id: Telegram user ID
        is_free: Whether a free image was reserved
    """
    if not is_free:
        # For paid images, we don't decrease anything upfront
        # So nothing to rollback
        return

    # Rollback free image
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id).with_for_update()
    )
    user = result.scalar_one_or_none()

    if user:
        user.free_images_left += 1
        await session.commit()


async def add_paid_images(session: AsyncSession, telegram_id: int, count: int):
    """This is tracked through orders, no direct operation needed"""
    pass


async def update_user_stats(session: AsyncSession, telegram_id: int) -> tuple[bool, int]:
    """
    Update user's total images processed counter

    Returns:
        Tuple of (is_first_image, user_id):
        - is_first_image: True if this was the first image processed for this user
        - user_id: Database user ID (for Metrika tracking)
    """
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()

    if user:
        # Check if this is the first image (before incrementing)
        is_first_image = (user.total_images_processed == 0)

        user.total_images_processed += 1
        user.updated_at = datetime.utcnow()
        await session.commit()

        return (is_first_image, user.id)

    return (False, 0)


# ==================== PACKAGE OPERATIONS ====================

async def get_all_packages(session: AsyncSession) -> List[Package]:
    """Get all active packages"""
    result = await session.execute(
        select(Package).where(Package.is_active == True).order_by(Package.images_count)
    )
    return result.scalars().all()


async def get_package_by_id(session: AsyncSession, package_id: int) -> Optional[Package]:
    """Get package by ID"""
    result = await session.execute(
        select(Package).where(Package.id == package_id)
    )
    return result.scalar_one_or_none()


async def sync_packages_from_config(session: AsyncSession, packages_config: List[dict]):
    """
    Synchronize packages from configuration to database
    Updates existing packages, creates new ones, and deactivates packages not in config

    Args:
        session: Database session
        packages_config: List of package configs from settings.packages_config
    """
    # Track IDs of packages that should be active
    active_package_ids = []

    for config in packages_config:
        name = config["name"]
        images_count = config["images_count"]
        price_rub = config["price_rub"]

        # Try to find existing package by name and images_count
        result = await session.execute(
            select(Package).where(
                and_(
                    Package.name == name,
                    Package.images_count == images_count
                )
            )
        )
        package = result.scalar_one_or_none()

        if package:
            # Update existing package
            package.price_rub = price_rub
            package.is_active = True
            active_package_ids.append(package.id)
        else:
            # Create new package
            package = Package(
                name=name,
                images_count=images_count,
                price_rub=price_rub,
                is_active=True
            )
            session.add(package)
            await session.flush()  # Get ID for newly created package
            active_package_ids.append(package.id)

    # Deactivate all packages that are not in config
    await session.execute(
        update(Package)
        .where(Package.id.not_in(active_package_ids))
        .values(is_active=False)
    )

    await session.commit()


# ==================== ORDER OPERATIONS ====================

async def create_order(session: AsyncSession, telegram_id: int, package_id: int,
                       invoice_id: str, amount: float) -> Order:
    """Create new order"""
    # Get user
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise ValueError("User not found")

    order = Order(
        user_id=user.id,
        package_id=package_id,
        invoice_id=invoice_id,
        amount=amount,
        status="pending"
    )
    session.add(order)
    await session.commit()
    await session.refresh(order)

    return order


async def get_order_by_invoice_id(session: AsyncSession, invoice_id: str) -> Optional[Order]:
    """Get order by YooKassa payment ID (stored in invoice_id field)"""
    result = await session.execute(
        select(Order).where(Order.invoice_id == invoice_id)
    )
    return result.scalar_one_or_none()


async def mark_order_paid(session: AsyncSession, invoice_id: str) -> Optional[Order]:
    """
    Mark order as paid and process referral rewards

    Returns:
        Order if it was marked as paid, None if order not found or already paid
    """
    order = await get_order_by_invoice_id(session, invoice_id)

    if not order:
        return None

    # Check if order is already paid - prevent duplicate processing
    if order.status == "paid":
        return None

    order.status = "paid"
    order.paid_at = datetime.utcnow()

    # Load user and package relationships for referral processing
    await session.refresh(order, ['user', 'package'])

    # Check if user was referred by someone
    if order.user.referred_by_id:
        from app.config import settings

        # Calculate referral reward (percentage of images purchased)
        images_purchased = order.package.images_count
        referral_reward = int(images_purchased * settings.REFERRAL_REWARD_PURCHASE_PERCENT / 100)

        if referral_reward > 0:
            # Add referral reward to referrer
            await add_referral_reward(
                session,
                user_id=order.user.referred_by_id,
                referred_user_id=order.user.id,
                reward_type='referral_purchase',
                images_rewarded=referral_reward,
                order_id=order.id
            )

    await session.commit()
    await session.refresh(order)

    return order


async def get_user_orders(session: AsyncSession, telegram_id: int, limit: int = 10) -> List[Order]:
    """Get user's orders"""
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        return []

    result = await session.execute(
        select(Order)
        .where(Order.user_id == user.id)
        .order_by(Order.created_at.desc())
        .limit(limit)
        .options(selectinload(Order.package))
    )
    return result.scalars().all()


# ==================== PROCESSED IMAGE OPERATIONS ====================

async def save_processed_image(session: AsyncSession, telegram_id: int, original_file_id: str,
                               processed_file_id: str, prompt_used: str, is_free: bool = False):
    """Save processed image record"""
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        return

    processed_image = ProcessedImage(
        user_id=user.id,
        original_file_id=original_file_id,
        processed_file_id=processed_file_id,
        prompt_used=prompt_used,
        is_free=is_free
    )
    session.add(processed_image)
    await session.commit()


# ==================== SUPPORT TICKET OPERATIONS ====================

async def create_support_ticket(session: AsyncSession, telegram_id: int, message: str,
                                order_id: Optional[int] = None) -> SupportTicket:
    """Create new support ticket"""
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise ValueError("User not found")

    ticket = SupportTicket(
        user_id=user.id,
        order_id=order_id,
        message=message,
        status="open"
    )
    session.add(ticket)
    await session.commit()
    await session.refresh(ticket)

    return ticket


async def get_open_tickets(session: AsyncSession) -> List[SupportTicket]:
    """Get all open support tickets"""
    result = await session.execute(
        select(SupportTicket)
        .where(SupportTicket.status.in_(["open", "in_progress"]))
        .order_by(SupportTicket.created_at.desc())
        .options(selectinload(SupportTicket.user))
    )
    return result.scalars().all()


async def get_ticket_by_id(session: AsyncSession, ticket_id: int) -> Optional[SupportTicket]:
    """Get support ticket by ID"""
    result = await session.execute(
        select(SupportTicket)
        .where(SupportTicket.id == ticket_id)
        .options(selectinload(SupportTicket.user), selectinload(SupportTicket.messages))
    )
    return result.scalar_one_or_none()


async def add_support_message(session: AsyncSession, ticket_id: int, sender_telegram_id: int,
                              message: str, is_admin: bool = False) -> SupportMessage:
    """Add message to support ticket"""
    support_message = SupportMessage(
        ticket_id=ticket_id,
        sender_telegram_id=sender_telegram_id,
        is_admin=is_admin,
        message=message
    )
    session.add(support_message)

    # Update ticket status if admin is responding
    if is_admin:
        result = await session.execute(
            select(SupportTicket).where(SupportTicket.id == ticket_id)
        )
        ticket = result.scalar_one_or_none()
        if ticket and ticket.status == "open":
            ticket.status = "in_progress"

    await session.commit()
    await session.refresh(support_message)
    return support_message


async def resolve_ticket(session: AsyncSession, ticket_id: int, admin_telegram_id: int, admin_response: str):
    """Resolve support ticket"""
    result = await session.execute(
        select(SupportTicket).where(SupportTicket.id == ticket_id)
    )
    ticket = result.scalar_one_or_none()

    if ticket:
        ticket.status = "resolved"
        ticket.admin_response = admin_response
        ticket.admin_id = admin_telegram_id
        ticket.resolved_at = datetime.utcnow()
        await session.commit()
        await session.refresh(ticket)

    return ticket


async def get_user_tickets(session: AsyncSession, telegram_id: int) -> List[SupportTicket]:
    """Get all tickets for a user"""
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        return []

    result = await session.execute(
        select(SupportTicket)
        .where(SupportTicket.user_id == user.id)
        .order_by(SupportTicket.created_at.desc())
        .options(selectinload(SupportTicket.messages))
    )
    return result.scalars().all()


# ==================== ADMIN OPERATIONS ====================

async def is_admin(session: AsyncSession, telegram_id: int) -> bool:
    """Check if user is admin"""
    result = await session.execute(
        select(Admin).where(Admin.telegram_id == telegram_id)
    )
    return result.scalar_one_or_none() is not None


async def get_statistics(session: AsyncSession) -> dict:
    """Get bot statistics"""
    # Total users
    users_result = await session.execute(select(func.count(User.id)))
    total_users = users_result.scalar() or 0

    # Total processed images
    images_result = await session.execute(select(func.count(ProcessedImage.id)))
    total_processed = images_result.scalar() or 0

    # Total revenue
    revenue_result = await session.execute(
        select(func.sum(Order.amount))
        .where(Order.status == "paid")
    )
    revenue = revenue_result.scalar() or 0

    # Active orders (pending)
    active_orders_result = await session.execute(
        select(func.count(Order.id))
        .where(Order.status == "pending")
    )
    active_orders = active_orders_result.scalar() or 0

    # Open tickets
    open_tickets_result = await session.execute(
        select(func.count(SupportTicket.id))
        .where(SupportTicket.status.in_(["open", "in_progress"]))
    )
    open_tickets = open_tickets_result.scalar() or 0

    # Total paid orders
    paid_orders_result = await session.execute(
        select(func.count(Order.id))
        .where(Order.status == "paid")
    )
    paid_orders = paid_orders_result.scalar() or 0

    # Free images processed
    free_images_result = await session.execute(
        select(func.count(ProcessedImage.id))
        .where(ProcessedImage.is_free == True)
    )
    free_images = free_images_result.scalar() or 0

    # Paid images processed
    paid_images_result = await session.execute(
        select(func.count(ProcessedImage.id))
        .where(ProcessedImage.is_free == False)
    )
    paid_images = paid_images_result.scalar() or 0

    return {
        "total_users": total_users,
        "total_processed": total_processed,
        "free_images_processed": free_images,
        "paid_images_processed": paid_images,
        "revenue": float(revenue),
        "active_orders": active_orders,
        "paid_orders": paid_orders,
        "open_tickets": open_tickets
    }


# ==================== UTM TRACKING OPERATIONS ====================

async def get_utm_statistics(session: AsyncSession) -> List[Dict[str, Any]]:
    """
    Get UTM statistics grouped by source, medium, campaign.

    Returns:
        List of dicts with UTM stats including users, conversions, revenue, etc.
    """
    # Query users with UTM data
    stmt = (
        select(
            User.utm_source,
            User.utm_medium,
            User.utm_campaign,
            func.count(User.id).label('total_users'),
            func.count(
                func.distinct(
                    case(
                        (Order.status == 'paid', Order.user_id),
                        else_=None
                    )
                )
            ).label('paying_users'),
            func.sum(
                case(
                    (Order.status == 'paid', Order.amount),
                    else_=0
                )
            ).label('revenue')
        )
        .outerjoin(Order, User.id == Order.user_id)
        .where(User.utm_source.isnot(None))
        .group_by(User.utm_source, User.utm_medium, User.utm_campaign)
        .order_by(desc('total_users'))
    )

    result = await session.execute(stmt)
    rows = result.all()

    stats = []
    for row in rows:
        total_users = row.total_users or 0
        paying_users = row.paying_users or 0
        revenue = float(row.revenue or 0)

        conversion_rate = (paying_users / total_users * 100) if total_users > 0 else 0
        arpu = (revenue / total_users) if total_users > 0 else 0

        stats.append({
            'utm_source': row.utm_source or 'unknown',
            'utm_medium': row.utm_medium or 'unknown',
            'utm_campaign': row.utm_campaign or 'unknown',
            'total_users': total_users,
            'paying_users': paying_users,
            'conversion_rate': round(conversion_rate, 2),
            'revenue': revenue,
            'arpu': round(arpu, 2)
        })

    return stats


async def get_utm_events_summary(session: AsyncSession, limit: int = 100) -> List[Dict[str, Any]]:
    """
    Get summary of recent UTM events.

    Args:
        session: Database session
        limit: Maximum number of events to return

    Returns:
        List of event summaries
    """
    stmt = (
        select(UTMEvent, User)
        .join(User, UTMEvent.user_id == User.id)
        .order_by(desc(UTMEvent.created_at))
        .limit(limit)
    )

    result = await session.execute(stmt)
    rows = result.all()

    events = []
    for event, user in rows:
        events.append({
            'event_id': event.id,
            'event_type': event.event_type,
            'user_id': user.telegram_id,
            'username': user.username,
            'utm_source': user.utm_source,
            'utm_medium': user.utm_medium,
            'utm_campaign': user.utm_campaign,
            'event_value': float(event.event_value) if event.event_value else None,
            'sent_to_metrika': event.sent_to_metrika,
            'created_at': event.created_at.isoformat() if event.created_at else None
        })

    return events


async def get_conversion_funnel(session: AsyncSession) -> Dict[str, Any]:
    """
    Get conversion funnel statistics for UTM sources.

    Returns:
        Dict with funnel metrics
    """
    # Total starts (users)
    total_starts = await session.execute(
        select(func.count(User.id))
        .where(User.utm_source.isnot(None))
    )
    starts = total_starts.scalar() or 0

    # Users with first image processed
    first_image_users = await session.execute(
        select(func.count(func.distinct(ProcessedImage.user_id)))
        .join(User, ProcessedImage.user_id == User.id)
        .where(User.utm_source.isnot(None))
    )
    first_images = first_image_users.scalar() or 0

    # Paying users
    paying_users = await session.execute(
        select(func.count(func.distinct(Order.user_id)))
        .join(User, Order.user_id == User.id)
        .where(and_(Order.status == 'paid', User.utm_source.isnot(None)))
    )
    purchases = paying_users.scalar() or 0

    return {
        'starts': starts,
        'first_images': first_images,
        'purchases': purchases,
        'start_to_first_image_rate': round((first_images / starts * 100) if starts > 0 else 0, 2),
        'first_image_to_purchase_rate': round((purchases / first_images * 100) if first_images > 0 else 0, 2),
        'overall_conversion_rate': round((purchases / starts * 100) if starts > 0 else 0, 2)
    }


async def get_utm_sync_status(session: AsyncSession) -> Dict[str, Any]:
    """
    Get Yandex Metrika synchronization status.

    Returns:
        Dict with sync statistics
    """
    # Total events
    total_events_result = await session.execute(
        select(func.count(UTMEvent.id))
    )
    total_events = total_events_result.scalar() or 0

    # Sent events
    sent_events_result = await session.execute(
        select(func.count(UTMEvent.id))
        .where(UTMEvent.sent_to_metrika == True)
    )
    sent_events = sent_events_result.scalar() or 0

    # Pending events
    pending_events = total_events - sent_events

    # Events by type (pending)
    pending_by_type = await session.execute(
        select(UTMEvent.event_type, func.count(UTMEvent.id))
        .where(UTMEvent.sent_to_metrika == False)
        .group_by(UTMEvent.event_type)
    )
    pending_breakdown = {row[0]: row[1] for row in pending_by_type}

    # Most recent sent event
    last_sent_result = await session.execute(
        select(UTMEvent.sent_at)
        .where(UTMEvent.sent_to_metrika == True)
        .order_by(desc(UTMEvent.sent_at))
        .limit(1)
    )
    last_sent_row = last_sent_result.first()
    last_sent = last_sent_row[0] if last_sent_row else None

    # Most recent pending event
    last_pending_result = await session.execute(
        select(UTMEvent.created_at)
        .where(UTMEvent.sent_to_metrika == False)
        .order_by(desc(UTMEvent.created_at))
        .limit(1)
    )
    last_pending_row = last_pending_result.first()
    last_pending = last_pending_row[0] if last_pending_row else None

    return {
        'total_events': total_events,
        'sent_events': sent_events,
        'pending_events': pending_events,
        'pending_breakdown': pending_breakdown,
        'last_sent_at': last_sent.isoformat() if last_sent else None,
        'last_pending_at': last_pending.isoformat() if last_pending else None,
        'sync_rate': round((sent_events / total_events * 100) if total_events > 0 else 0, 2)
    }

# ==================== REFERRAL PROGRAM OPERATIONS ====================

async def generate_referral_code(session: AsyncSession) -> str:
    """
    Generate unique referral code for user.
    Format: 6-character alphanumeric code (uppercase)
    
    Returns:
        Unique referral code
    """
    import random
    import string
    
    while True:
        # Generate random 6-character code
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        
        # Check if code already exists
        result = await session.execute(
            select(User).where(User.referral_code == code)
        )
        existing = result.scalar_one_or_none()
        
        if not existing:
            return code


async def get_or_create_referral_code(session: AsyncSession, user_id: int) -> str:
    """
    Get user's referral code or create new one if doesn't exist.
    
    Args:
        session: Database session
        user_id: User's database ID
        
    Returns:
        User's referral code
    """
    result = await session.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one()
    
    if not user.referral_code:
        user.referral_code = await generate_referral_code(session)
        await session.commit()
        await session.refresh(user)
    
    return user.referral_code


async def get_user_by_referral_code(session: AsyncSession, referral_code: str) -> Optional[User]:
    """
    Get user by their referral code.
    
    Args:
        session: Database session
        referral_code: Referral code to search for
        
    Returns:
        User object or None
    """
    result = await session.execute(
        select(User).where(User.referral_code == referral_code)
    )
    return result.scalar_one_or_none()


async def set_user_referrer(
    session: AsyncSession,
    user_id: int,
    referrer_id: int
) -> bool:
    """
    Set referrer for a user (only if not already set).
    
    Args:
        session: Database session
        user_id: User being referred
        referrer_id: User who referred them
        
    Returns:
        True if referrer was set, False if already had referrer
    """
    result = await session.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one()
    
    # Only set referrer if user doesn't have one already and isn't referring themselves
    if not user.referred_by_id and user_id != referrer_id:
        user.referred_by_id = referrer_id
        
        # Increment referrer's total_referrals count
        await session.execute(
            update(User)
            .where(User.id == referrer_id)
            .values(total_referrals=User.total_referrals + 1)
        )
        
        await session.commit()
        return True
    
    return False


async def add_referral_reward(
    session: AsyncSession,
    user_id: int,
    referred_user_id: int,
    reward_type: str,
    images_rewarded: int,
    order_id: Optional[int] = None
) -> ReferralReward:
    """
    Add referral reward to user and create reward record.
    
    Args:
        session: Database session
        user_id: User receiving reward
        referred_user_id: User who was referred
        reward_type: Type of reward ('referral_start' or 'referral_purchase')
        images_rewarded: Number of images to reward
        order_id: Related order ID (for purchase rewards)
        
    Returns:
        Created ReferralReward object
    """
    # Add images to user's free_images_left
    await session.execute(
        update(User)
        .where(User.id == user_id)
        .values(free_images_left=User.free_images_left + images_rewarded)
    )
    
    # Create reward record
    reward = ReferralReward(
        user_id=user_id,
        referred_user_id=referred_user_id,
        order_id=order_id,
        reward_type=reward_type,
        images_rewarded=images_rewarded
    )
    session.add(reward)
    await session.commit()
    await session.refresh(reward)
    
    return reward


async def get_referral_stats(session: AsyncSession, user_id: int) -> Dict[str, Any]:
    """
    Get referral statistics for a user.
    
    Args:
        session: Database session
        user_id: User's database ID
        
    Returns:
        Dict with referral stats
    """
    # Get user with referrals
    result = await session.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one()
    
    # Get total rewards earned
    rewards_result = await session.execute(
        select(func.sum(ReferralReward.images_rewarded))
        .where(ReferralReward.user_id == user_id)
    )
    total_rewards = rewards_result.scalar() or 0
    
    # Get rewards by type
    rewards_by_type_result = await session.execute(
        select(ReferralReward.reward_type, func.sum(ReferralReward.images_rewarded))
        .where(ReferralReward.user_id == user_id)
        .group_by(ReferralReward.reward_type)
    )
    rewards_by_type = {row[0]: row[1] for row in rewards_by_type_result}
    
    return {
        'total_referrals': user.total_referrals,
        'total_rewards': int(total_rewards),
        'rewards_from_start': int(rewards_by_type.get('referral_start', 0)),
        'rewards_from_purchases': int(rewards_by_type.get('referral_purchase', 0)),
        'referral_code': user.referral_code
    }
