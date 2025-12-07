from datetime import datetime
from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB
from typing import Optional, List


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    free_images_left: Mapped[int] = mapped_column(Integer, default=3)
    total_images_processed: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # UTM tracking fields
    utm_source: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)  # yandex, google, direct
    utm_medium: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)  # cpc, rsya, organic
    utm_campaign: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)  # sellers_wb, retargeting
    utm_content: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # ad1, banner2
    utm_term: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # keyword

    # Yandex Metrika unique identifier (UUID v4)
    metrika_client_id: Mapped[Optional[str]] = mapped_column(String(36), unique=True, nullable=True, index=True)

    # Referral program fields
    referred_by_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)  # Who referred this user
    referral_code: Mapped[Optional[str]] = mapped_column(String(20), unique=True, nullable=True, index=True)  # User's unique referral code
    total_referrals: Mapped[int] = mapped_column(Integer, default=0)  # Count of referred users

    # Relationships
    orders: Mapped[List["Order"]] = relationship("Order", back_populates="user")
    processed_images: Mapped[List["ProcessedImage"]] = relationship("ProcessedImage", back_populates="user")
    support_tickets: Mapped[List["SupportTicket"]] = relationship("SupportTicket", back_populates="user")
    utm_events: Mapped[List["UTMEvent"]] = relationship("UTMEvent", back_populates="user", cascade="all, delete-orphan")

    # Referral relationships
    referrer: Mapped[Optional["User"]] = relationship("User", remote_side=[id], foreign_keys=[referred_by_id], back_populates="referrals")
    referrals: Mapped[List["User"]] = relationship("User", foreign_keys=[referred_by_id], back_populates="referrer", cascade="all, delete-orphan")
    referral_rewards: Mapped[List["ReferralReward"]] = relationship("ReferralReward", foreign_keys="[ReferralReward.user_id]", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id={self.id}, telegram_id={self.telegram_id}, username={self.username})>"


class Package(Base):
    __tablename__ = "packages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    images_count: Mapped[int] = mapped_column(Integer, nullable=False)
    price_rub: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    orders: Mapped[List["Order"]] = relationship("Order", back_populates="package")

    def __repr__(self):
        return f"<Package(id={self.id}, name={self.name}, images={self.images_count}, price={self.price_rub})>"


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))
    package_id: Mapped[int] = mapped_column(Integer, ForeignKey("packages.id"))
    invoice_id: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True)  # YooKassa payment_id
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending")  # pending, paid, refunded
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="orders")
    package: Mapped["Package"] = relationship("Package", back_populates="orders")
    processed_images: Mapped[List["ProcessedImage"]] = relationship("ProcessedImage", back_populates="order")
    support_tickets: Mapped[List["SupportTicket"]] = relationship("SupportTicket", back_populates="order")

    def __repr__(self):
        return f"<Order(id={self.id}, user_id={self.user_id}, status={self.status}, amount={self.amount})>"


class ProcessedImage(Base):
    __tablename__ = "processed_images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))
    order_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("orders.id"), nullable=True)
    original_file_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    processed_file_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    prompt_used: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_free: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="processed_images")
    order: Mapped[Optional["Order"]] = relationship("Order", back_populates="processed_images")

    def __repr__(self):
        return f"<ProcessedImage(id={self.id}, user_id={self.user_id}, is_free={self.is_free})>"


class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))
    order_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("orders.id"), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="open")  # open, in_progress, resolved
    admin_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    admin_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)  # Telegram ID of admin handling the ticket
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="support_tickets")
    order: Mapped[Optional["Order"]] = relationship("Order", back_populates="support_tickets")
    messages: Mapped[List["SupportMessage"]] = relationship("SupportMessage", back_populates="ticket", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<SupportTicket(id={self.id}, user_id={self.user_id}, status={self.status})>"


class SupportMessage(Base):
    __tablename__ = "support_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(Integer, ForeignKey("support_tickets.id"))
    sender_telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    ticket: Mapped["SupportTicket"] = relationship("SupportTicket", back_populates="messages")

    def __repr__(self):
        return f"<SupportMessage(id={self.id}, ticket_id={self.ticket_id}, is_admin={self.is_admin})>"


class Admin(Base):
    __tablename__ = "admins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(50), default="admin")  # admin, super_admin
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Admin(id={self.id}, telegram_id={self.telegram_id}, role={self.role})>"


class UTMEvent(Base):
    """
    UTM events tracking for analytics and Yandex Metrika integration.
    Events are stored in database regardless of Metrika configuration.
    """
    __tablename__ = "utm_events"
    __table_args__ = (
        Index('idx_utm_events_user_type', 'user_id', 'event_type'),
        Index('idx_utm_events_created', 'created_at'),
        Index('idx_utm_events_sent', 'sent_to_metrika'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)

    # Event identification
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # start, first_image, purchase, etc.
    metrika_client_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)  # UUID for Metrika

    # Event details
    event_value: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)  # Revenue for purchases
    currency: Mapped[Optional[str]] = mapped_column(String(3), nullable=True, default="RUB")  # Currency code
    event_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)  # Additional JSON data

    # Metrika integration status
    sent_to_metrika: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    metrika_upload_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # Metrika upload ID

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="utm_events")

    def __repr__(self):
        return f"<UTMEvent(id={self.id}, user_id={self.user_id}, event_type={self.event_type}, sent={self.sent_to_metrika})>"


class ReferralReward(Base):
    """
    Referral rewards tracking - logs all rewards given to referrers.
    Tracks both rewards for new referrals and percentage rewards from purchases.
    """
    __tablename__ = "referral_rewards"
    __table_args__ = (
        Index('idx_referral_rewards_user_type', 'user_id', 'reward_type'),
        Index('idx_referral_rewards_created', 'created_at'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)  # User receiving reward
    referred_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)  # User who was referred
    order_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("orders.id"), nullable=True)  # Related order (for purchase rewards)

    # Reward details
    reward_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # 'referral_start', 'referral_purchase'
    images_rewarded: Mapped[int] = mapped_column(Integer, nullable=False)  # Number of images given as reward
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    # Relationships
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id], back_populates="referral_rewards")
    referred_user: Mapped["User"] = relationship("User", foreign_keys=[referred_user_id])
    order: Mapped[Optional["Order"]] = relationship("Order", foreign_keys=[order_id])

    def __repr__(self):
        return f"<ReferralReward(id={self.id}, user_id={self.user_id}, type={self.reward_type}, images={self.images_rewarded})>"
