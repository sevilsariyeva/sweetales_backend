from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, Float, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base


class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    image = Column(String, nullable=True)
    subscription = Column(String, default="Free")
    is_active = Column(Boolean, default=True)
    credits = Column(Integer, default=5)  # Start with 5 free credits
    # FIX: Ensure timestamps are properly set
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    stories = relationship("Story", back_populates="user", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="user", cascade="all, delete-orphan")
    activities = relationship("UserActivity", back_populates="user", cascade="all, delete-orphan")
    favorite_stories = relationship("StoryFavorite", back_populates="user", cascade="all, delete-orphan")


class Plan(Base):
    __tablename__ = "plans"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    credits = Column(Integer, nullable=False)
    price = Column(Float, nullable=False)
    popular = Column(Boolean, default=False)
    description = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    lemonsqueezy_variant_id = Column(String, nullable=True)
    
    # Relationships
    transactions = relationship("Transaction", back_populates="plan")
    paddle_price_id = Column(String, nullable=True)


class Story(Base):
    __tablename__ = "stories"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    title = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    language = Column(String, nullable=False, default="en")
    genre = Column(String, nullable=True, default="adventure")
    audio_url = Column(String, nullable=True)  # This is the main audio field
    has_audio = Column(Boolean, default=False)  # Flag to indicate if audio exists
    audio_filename = Column(String, nullable=True)  # Keep for backward compatibility
    voice = Column(String, default="grandma")
    image_filename = Column(String, nullable=True)
    word_count = Column(Integer, default=0)
    character_count = Column(Integer, default=0)
    reading_time = Column(Integer, default=1)  # in minutes
    # FIX: Ensure timestamps are properly set and not nullable
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="stories")
    favorited_by = relationship("StoryFavorite", back_populates="story", cascade="all, delete-orphan")


class StoryFavorite(Base):
    __tablename__ = "story_favorites"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    story_id = Column(Integer, ForeignKey("stories.id", ondelete="CASCADE"))
    # FIX: Ensure timestamp is properly set and not nullable
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Ensure one user can favorite one story only once
    __table_args__ = (UniqueConstraint('user_id', 'story_id', name='unique_user_story_favorite'),)
    
    # Relationships
    user = relationship("User", back_populates="favorite_stories")
    story = relationship("Story", back_populates="favorited_by")


class Transaction(Base):
    __tablename__ = "transactions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    plan_id = Column(Integer, ForeignKey("plans.id"), nullable=False)
    amount = Column(Float, nullable=False)
    credits_purchased = Column(Integer, nullable=False)
    status = Column(String, default="pending")
    stripe_session_id = Column(String, nullable=True)
    stripe_payment_intent_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="transactions")
    plan = relationship("Plan", back_populates="transactions")
    paddle_transaction_id = Column(String, nullable=True)


class UserActivity(Base):
    __tablename__ = "user_activities"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    activity_type = Column(String(50), nullable=False)  # 'story_created', 'credits_purchased', 'story_favorited', etc.
    description = Column(Text, nullable=False)  # Human readable description
    related_id = Column(Integer, nullable=True)  # ID of related story, transaction, etc.
    # FIX: Ensure timestamp is properly set and not nullable
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Relationship
    user = relationship("User", back_populates="activities")