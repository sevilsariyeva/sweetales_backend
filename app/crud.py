from sqlalchemy.orm import Session
from sqlalchemy import desc, func, and_
from datetime import datetime, timedelta
from typing import List, Optional
import math
from . import models, schemas, auth


# ===============================
# User CRUD
# ===============================
def get_user(db: Session, user_id: int) -> Optional[models.User]:
    return db.query(models.User).filter(models.User.id == user_id).first()

def get_user_by_email(db: Session, email: str) -> Optional[models.User]:
    return db.query(models.User).filter(models.User.email == email).first()

def get_user_by_username(db: Session, username: str) -> Optional[models.User]:
    return db.query(models.User).filter(models.User.username == username).first()

def create_user(db: Session, user: schemas.UserCreate) -> models.User:
    hashed_password = auth.get_password_hash(user.password)
    current_time = datetime.utcnow()
    db_user = models.User(
        email=user.email,
        username=user.username,
        hashed_password=hashed_password,
        credits=5,  # start with 5 free credits
        created_at=current_time,
        updated_at=current_time
    )
    db.add(db_user)
    try:
        db.commit()
        db.refresh(db_user)
        return db_user
    except Exception as e:
        db.rollback()
        raise e

def update_user_credits(db: Session, user_id: int, credits: int) -> Optional[models.User]:
    db_user = get_user(db, user_id)
    if not db_user:
        return None
    db_user.credits += credits
    db_user.updated_at = datetime.utcnow()
    try:
        db.commit()
        db.refresh(db_user)
        return db_user
    except Exception as e:
        db.rollback()
        raise e

def deduct_user_credits(db: Session, user_id: int, credits: int = 5) -> Optional[models.User]:
    db_user = get_user(db, user_id)
    if not db_user or db_user.credits < credits:
        return None
    db_user.credits -= credits
    db_user.updated_at = datetime.utcnow()
    try:
        db.commit()
        db.refresh(db_user)
        return db_user
    except Exception as e:
        db.rollback()
        raise e

def update_user_profile(db: Session, user_id: int, profile_data: schemas.UserUpdate) -> Optional[models.User]:
    db_user = get_user(db, user_id)
    if not db_user:
        return None

    if profile_data.username:
        if db.query(models.User).filter(
            models.User.username == profile_data.username,
            models.User.id != user_id
        ).first():
            raise ValueError("Username already exists")
        db_user.username = profile_data.username

    if profile_data.email:
        if db.query(models.User).filter(
            models.User.email == profile_data.email,
            models.User.id != user_id
        ).first():
            raise ValueError("Email already exists")
        db_user.email = profile_data.email

    db_user.updated_at = datetime.utcnow()
    try:
        db.commit()
        db.refresh(db_user)
        create_user_activity(db, user_id, "profile_updated", "Updated profile information")
        return db_user
    except Exception as e:
        db.rollback()
        raise e

def update_user_avatar(db: Session, user_id: int, avatar_url: str) -> Optional[models.User]:
    db_user = get_user(db, user_id)
    if not db_user:
        return None
    db_user.image = avatar_url
    db_user.updated_at = datetime.utcnow()
    try:
        db.commit()
        db.refresh(db_user)
        create_user_activity(db, user_id, "avatar_updated", "Updated profile picture")
        return db_user
    except Exception as e:
        db.rollback()
        raise e

def update_user_password(db: Session, user_id: int, new_password: str) -> bool:
    db_user = get_user(db, user_id)
    if not db_user:
        return False
    db_user.hashed_password = auth.get_password_hash(new_password)
    db_user.updated_at = datetime.utcnow()
    try:
        db.commit()
        create_user_activity(db, user_id, "password_changed", "Changed account password")
        return True
    except Exception as e:
        db.rollback()
        raise e


# ===============================
# Stories CRUD
# ===============================
def create_story(db: Session, story_data: dict, user_id: int) -> models.Story:
    content = story_data.get("content", "")
    word_count = len(content.split())
    character_count = len(content)
    reading_time = max(1, math.ceil(word_count / 200))  # 200 WPM

    current_time = datetime.utcnow()
    db_story = models.Story(
        title=story_data.get("title", "Untitled Story"),
        content=content,
        language=story_data.get("language", "en"),
        genre=story_data.get("genre", "adventure"),
        audio_url=story_data.get("audio_url"),
        has_audio=story_data.get("has_audio", False),
        image_filename=story_data.get("image_filename"),
        voice=story_data.get("voice", "grandma"),
        word_count=word_count,
        character_count=character_count,
        reading_time=reading_time,
        user_id=user_id,
        created_at=current_time,
        updated_at=current_time
    )
    db.add(db_story)
    try:
        db.commit()
        db.refresh(db_story)
        create_user_activity(db, user_id, "story_created", f"Created new story: {db_story.title}", db_story.id)
        return db_story
    except Exception as e:
        db.rollback()
        raise e

def get_user_stories(db: Session, user_id: int, limit: Optional[int] = None, offset: int = 0) -> List[models.Story]:
    q = db.query(models.Story).filter(models.Story.user_id == user_id).order_by(desc(models.Story.created_at))
    if offset:
        q = q.offset(offset)
    if limit:
        q = q.limit(limit)
    return q.all()

def get_user_stories_count(db: Session, user_id: int) -> int:
    return db.query(models.Story).filter(models.Story.user_id == user_id).count()

def get_story_by_id(db: Session, story_id: int, user_id: int) -> Optional[models.Story]:
    return db.query(models.Story).filter(
        models.Story.id == story_id,
        models.Story.user_id == user_id
    ).first()

def update_story_audio(db: Session, story_id: int, user_id: int, audio_url: str, voice: str = "grandma") -> Optional[models.Story]:
    db_story = get_story_by_id(db, story_id, user_id)
    if not db_story:
        return None
    db_story.audio_url = audio_url
    db_story.has_audio = True
    db_story.voice = voice
    db_story.updated_at = datetime.utcnow()
    try:
        db.commit()
        db.refresh(db_story)
        create_user_activity(db, user_id, "audio_generated", f"Generated {voice} audio for {db_story.title}", story_id)
        return db_story
    except Exception as e:
        db.rollback()
        raise e

def delete_story(db: Session, story_id: int, user_id: int) -> bool:
    db_story = get_story_by_id(db, story_id, user_id)
    if not db_story:
        return False
    story_title = db_story.title
    try:
        db.delete(db_story)
        db.commit()
        # Log activity with proper timestamp
        create_user_activity(db, user_id, "story_deleted", f"Deleted story: {story_title}")
        return True
    except Exception:
        db.rollback()
        raise

def toggle_story_favorite(db: Session, story_id: int, user_id: int) -> bool:
    # Check if story exists and belongs to user
    db_story = get_story_by_id(db, story_id, user_id)
    if not db_story:
        return False
    
    # Check if already favorited
    favorite = db.query(models.StoryFavorite).filter(
        and_(
            models.StoryFavorite.story_id == story_id,
            models.StoryFavorite.user_id == user_id
        )
    ).first()
    
    current_time = datetime.utcnow()
    print(current_time)
    
    try:
        if favorite:
            # Remove favorite
            db.delete(favorite)
            is_favorite = False
            activity_type = "story_unfavorited"
            description = f"Unfavorited story: {db_story.title}"
        else:
            # Add favorite with explicit timestamp
            new_favorite = models.StoryFavorite(
                story_id=story_id, 
                user_id=user_id,
                created_at=current_time
            )
            db.add(new_favorite)
            is_favorite = True
            activity_type = "story_favorited"
            description = f"Favorited story: {db_story.title}"
        
        # Commit the favorite/unfavorite operation first
        db.commit()
        
        # Then log activity with proper timestamp (this creates its own transaction)
        create_user_activity(db, user_id, activity_type, description, story_id)
        
        return is_favorite
        
    except Exception:
        db.rollback()
        raise
def get_favorite_stories(db: Session, user_id: int, limit: Optional[int] = None, offset: int = 0) -> List[models.Story]:
    query = db.query(models.Story).join(
        models.StoryFavorite, 
        models.Story.id == models.StoryFavorite.story_id
    ).filter(
        models.StoryFavorite.user_id == user_id
    ).order_by(desc(models.StoryFavorite.created_at))
    
    if offset:
        query = query.offset(offset)
    if limit:
        query = query.limit(limit)
    return query.all()

def get_favorite_stories_count(db: Session, user_id: int) -> int:
    return db.query(models.StoryFavorite).filter(models.StoryFavorite.user_id == user_id).count()

def get_stories_by_genre(db: Session, user_id: int, genre: str, limit: Optional[int] = None) -> List[models.Story]:
    query = db.query(models.Story).filter(
        models.Story.user_id == user_id, 
        models.Story.genre == genre
    ).order_by(desc(models.Story.created_at))
    if limit:
        query = query.limit(limit)
    return query.all()

def get_user_story_stats(db: Session, user_id: int) -> dict:
    total_stories = get_user_stories_count(db, user_id)
    favorite_count = get_favorite_stories_count(db, user_id)
    audio_stories = db.query(models.Story).filter(
        models.Story.user_id == user_id, 
        models.Story.has_audio == True
    ).count()
    
    genre_stats = db.query(
        models.Story.genre, 
        func.count(models.Story.id).label('count')
    ).filter(
        models.Story.user_id == user_id
    ).group_by(models.Story.genre).all()
    
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    recent_stories = db.query(models.Story).filter(
        models.Story.user_id == user_id, 
        models.Story.created_at >= thirty_days_ago
    ).count()
    
    return {
        "total_stories": total_stories,
        "favorite_stories": favorite_count,
        "stories_with_audio": audio_stories,
        "recent_stories_30_days": recent_stories,
        "genres": [{"genre": g.genre, "count": g.count} for g in genre_stats]
    }


# ===============================
# User Activity CRUD - FIXED
# ===============================
def create_user_activity(db: Session, user_id: int, activity_type: str, description: str, related_id: int = None):
    """Create user activity with explicit timestamp"""
    current_time = datetime.utcnow()
    activity = models.UserActivity(
        user_id=user_id, 
        activity_type=activity_type, 
        description=description,
        related_id=related_id,
        created_at=current_time  # Explicitly set the timestamp
    )
    db.add(activity)
    try:
        db.commit()
        db.refresh(activity)
        print(f"Activity created: {activity.id}, created_at: {activity.created_at}, related_id: {activity.related_id}")
        return activity
    except Exception as e:
        print(f"Error creating activity: {e}")
        db.rollback()
        raise

def get_user_activities(db: Session, user_id: int, limit: int = 20) -> List[models.UserActivity]:
    return db.query(models.UserActivity).filter(
        models.UserActivity.user_id == user_id
    ).order_by(desc(models.UserActivity.created_at)).limit(limit).all()

def log_profile_updated(db: Session, user_id: int):
    create_user_activity(db, user_id, "profile_updated", "Updated profile information")

def log_password_changed(db: Session, user_id: int):
    create_user_activity(db, user_id, "password_changed", "Changed account password")

def log_story_created(db: Session, user_id: int, story_title: str, story_id: int):
    create_user_activity(db, user_id, "story_created", f"Created new story: {story_title}", story_id)

def log_story_favorited(db: Session, user_id: int, story_title: str, story_id: int):
    create_user_activity(db, user_id, "story_favorited", f"Favorited story: {story_title}", story_id)

def log_story_unfavorited(db: Session, user_id: int, story_title: str, story_id: int):
    create_user_activity(db, user_id, "story_unfavorited", f"Unfavorited story: {story_title}", story_id)

def log_audio_generated(db: Session, user_id: int, story_title: str, story_id: int):
    create_user_activity(db, user_id, "audio_generated", f"Generated audio for story: {story_title}", story_id)

def log_story_deleted(db: Session, user_id: int, story_title: str):
    create_user_activity(db, user_id, "story_deleted", f"Deleted story: {story_title}")

def log_avatar_updated(db: Session, user_id: int):
    create_user_activity(db, user_id, "avatar_updated", "Updated profile picture")


# ===============================
# Plans CRUD
# ===============================
def get_plans(db: Session):
    """Bütün planları qaytarır"""
    return db.query(models.Plan).all()

def get_plan(db: Session, plan_id: int):
    """Plan ID-yə görə plan qaytarır"""
    return db.query(models.Plan).filter(models.Plan.id == plan_id).first()

def create_plan(db: Session, name: str, credits: int, price: float, popular: bool = False, description: str = None):
    """Yeni plan yaradır (admin üçün)"""
    plan = models.Plan(
        name=name,
        credits=credits,
        price=price,
        popular=popular,
        description=description
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan

# ===============================
# Transactions CRUD - FIXED
# ===============================
def create_transaction(
    db: Session, 
    user_id: int, 
    plan_id: int, 
    amount: float, 
    credits: int,
    status: str = "pending"
):
    """Yeni transaction yaradır"""
    transaction = models.Transaction(
        user_id=user_id,
        plan_id=plan_id,
        amount=amount,
        credits_purchased=credits,
        status=status,
        created_at=datetime.utcnow()
    )
    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    return transaction


def update_transaction_status(
    db: Session, 
    transaction_id: int, 
    status: str, 
    payment_intent_id: str = None
):
    """Transaction statusunu yeniləyir"""
    transaction = db.query(models.Transaction).filter(
        models.Transaction.id == transaction_id
    ).first()
    
    if transaction:
        transaction.status = status
        transaction.updated_at = datetime.utcnow()
        if payment_intent_id:
            transaction.stripe_payment_intent_id = payment_intent_id
        db.commit()
        db.refresh(transaction)
    
    return transaction


def get_user_transactions(db: Session, user_id: int, limit: int = 50):
    return db.query(models.Transaction).filter(
        models.Transaction.user_id == user_id
    ).order_by(models.Transaction.created_at.desc()).limit(limit).all()
def log_credit_purchase(db: Session, user_id: int, credits: int, amount_paid: float):
    create_transaction(db, user_id, "purchase", credits, f"Purchased {credits} credits for ${amount_paid}")

def log_credit_deduction(db: Session, user_id: int, credits: int, reason: str):
    create_transaction(db, user_id, "deduction", -credits, f"Used {credits} credits for {reason}")

def log_credit_bonus(db: Session, user_id: int, credits: int, reason: str):
    create_transaction(db, user_id, "bonus", credits, f"Received {credits} bonus credits: {reason}")