from pydantic import BaseModel,Field, EmailStr, validator
from typing import Optional, List
from datetime import datetime

# ===============================
# User Activity schemas - FIXED
# ===============================
class ActivityBase(BaseModel):
    activity_type: str
    description: str
    related_id: Optional[int] = None

class ActivityCreate(ActivityBase):
    user_id: int

class Activity(ActivityBase):
    id: int
    user_id: int
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        from_attributes = True

# ===============================
# User schemas - FIXED
# ===============================
class UserBase(BaseModel):
    username: str
    email: EmailStr

class UserCreate(UserBase):
    password: str

class UserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[EmailStr] = None

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class User(UserBase):
    id: int
    is_active: bool = True
    credits: int = 0
    image: Optional[str] = None
    subscription: str = "Free"
    created_at: Optional[datetime] = None
    activities: Optional[List[Activity]] = []
    
    # FIX: Add validator to handle null datetime values
    @validator('created_at', pre=True)
    def validate_created_at(cls, v):
        if v is None:
            return datetime.utcnow()
        return v
    
    class Config:
        from_attributes = True

class PasswordChange(BaseModel):
    current_password: str
    new_password: str

# ===============================
# Token schemas
# ===============================
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

# ===============================
# Story schemas - FIXED
# ===============================
class StoryBase(BaseModel):
    title: str
    content: Optional[str] = None
    genre: Optional[str] = None

class StoryCreate(StoryBase):
    language: Optional[str] = None

class StoryUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    genre: Optional[str] = None
    audio_url: Optional[str] = None

class Story(StoryBase):
    id: int
    user_id: int
    language: Optional[str] = None
    audio_url: Optional[str] = None
    audio_filename: Optional[str] = None
    image_filename: Optional[str] = None
    has_audio: bool = False
    word_count: int = 0
    character_count: int = 0
    reading_time: int = 1
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    # FIX: Add validators to handle null datetime values
    @validator('created_at', 'updated_at', pre=True)
    def validate_timestamps(cls, v):
        if v is None:
            return datetime.utcnow()
        return v
    
    class Config:
        from_attributes = True

class StoryWithStats(Story):
    character_count: int = 0
    word_count: int = 0
    is_favorite: bool = False

class StoryFavoriteBase(BaseModel):
    story_id: int

class StoryFavoriteCreate(StoryFavoriteBase):
    pass

class StoryFavorite(StoryFavoriteBase):
    id: int
    user_id: int
    created_at: Optional[datetime] = None
    
    # FIX: Add validator to handle null datetime values
    @validator('created_at', pre=True)
    def validate_created_at(cls, v):
        if v is None:
            return datetime.utcnow()
        return v
    
    class Config:
        from_attributes = True

class StoryListResponse(BaseModel):
    stories: List[StoryWithStats]
    total_count: int
    current_page: int = 1
    total_pages: int = 1

class StoryStatsResponse(BaseModel):
    total_stories: int
    favorite_stories: int
    stories_with_audio: int
    recent_stories_30_days: int
    genres: List[dict]

class StoryResponse(BaseModel):
    success: bool
    story: str
    audioUrl: str
    fullAudioUrl: str
    message: str
    audioFileName: str
    user_credits: int

# ===============================
# Plan schemas
# ===============================
class PlanBase(BaseModel):
    name: str
    credits: int
    price: float
    popular: bool = False
    description: Optional[str] = None

class Plan(PlanBase):
    id: int
    created_at: datetime
    
    class Config:
        from_attributes = True


class TransactionBase(BaseModel):
    amount: float
    credits_purchased: int
    status: str

class Transaction(TransactionBase):
    id: int
    user_id: int
    plan_id: int
    stripe_session_id: Optional[str] = None
    stripe_payment_intent_id: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class TransactionCreate(BaseModel):
    plan_id: int


class CheckoutSessionResponse(BaseModel):
    session_id: str
    url: str
    transaction_id: int


class PaymentStatusResponse(BaseModel):
    status: str
    credits: Optional[int] = None
    message: str

# ===============================
# Dashboard response - FIXED
# ===============================
class DashboardResponse(BaseModel):
    user: User
    recent_stories: List[Story]
    recent_transactions: List[dict] = []
    recent_activities: List[Activity]
    total_stories: int
    credits: int