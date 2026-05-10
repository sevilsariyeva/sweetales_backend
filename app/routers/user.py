# routers/user.py - Fixed and complete

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status, Query
from sqlalchemy.orm import Session
from typing import Optional
import shutil
import os
import math
from pathlib import Path

from .. import crud, models, schemas, auth
from ..database import get_db

router = APIRouter(
    prefix="/user",
    tags=["user"]
)

@router.get("/profile", response_model=schemas.User)
def get_profile(current_user: models.User = Depends(auth.get_current_active_user)):
    """Get current user profile"""
    return current_user

@router.put("/profile")
def update_profile(
    profile_data: schemas.UserUpdate,
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db)
):
    """Update user profile information"""
    try:
        # Update user profile
        updated_user = crud.update_user_profile(db, current_user.id, profile_data)
        if not updated_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail="User not found"
            )
        
        # Log the activity
        crud.log_profile_updated(db, current_user.id)
        
        return {
            "message": "Profile updated successfully",
            "user": updated_user
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=str(e)
        )
    except Exception as e:
        print(f"Error updating profile: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Internal server error"
        )

@router.put("/profile/avatar")
def update_avatar(
    file: UploadFile = File(...),
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db)
):
    """Update user profile picture"""
    # Validate file type
    allowed_types = ["image/jpeg", "image/jpg", "image/png", "image/gif", "image/webp"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Invalid file type. Only JPEG, PNG, GIF, and WebP are allowed."
        )
    
    try:
        # Create uploads directory if it doesn't exist
        upload_dir = Path("uploads/avatars")
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate filename
        file_extension = file.filename.split(".")[-1] if file.filename else "jpg"
        filename = f"user_{current_user.id}.{file_extension}"
        file_path = upload_dir / filename
        
        # Save file
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Update user's avatar path in database
        avatar_url = f"/uploads/avatars/{filename}"
        updated_user = crud.update_user_avatar(db, current_user.id, avatar_url)
        
        # Log the activity
        crud.create_user_activity(db, current_user.id, "avatar_updated", "Updated profile picture")
        
        return {
            "message": "Avatar updated successfully", 
            "avatar_url": avatar_url,
            "user": updated_user
        }
    
    except Exception as e:
        print(f"Error uploading avatar: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"Could not upload file: {str(e)}"
        )

@router.put("/change-password")
def change_password(
    password_data: schemas.PasswordChange,
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db)
):
    """Change user password"""
    # Verify current password
    if not auth.verify_password(password_data.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Current password is incorrect"
        )
    
    # Validate new password length
    if len(password_data.new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be at least 8 characters long"
        )
    
    # Update password
    try:
        success = crud.update_user_password(db, current_user.id, password_data.new_password)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="Failed to update password"
            )
        
        # Log the activity
        crud.log_password_changed(db, current_user.id)
        
        return {"message": "Password updated successfully"}
    except Exception as e:
        print(f"Error changing password: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Internal server error"
        )

@router.get("/credits")
def get_credits(current_user: models.User = Depends(auth.get_current_active_user)):
    """Get user credits"""
    return {"credits": current_user.credits}

@router.get("/dashboard")
def get_dashboard(
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get user dashboard data"""
    stories = crud.get_user_stories(db, current_user.id, limit=5)
    transactions = crud.get_user_transactions(db, current_user.id, limit=5)
    # Increase limit for recent activities to show more
    recent_activities = crud.get_user_activities(db, current_user.id, limit=15)
    favorite_stories_count = crud.get_favorite_stories_count(db, current_user.id)

    return {
        "user": current_user,
        "recent_stories": stories,
        "recent_transactions": transactions,
        "recent_activities": recent_activities,
        "total_stories": crud.get_user_stories_count(db, current_user.id),
        "credits": current_user.credits,
        "favorite_stories": favorite_stories_count,
    }

@router.get("/activities")
def get_user_activities_endpoint(
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
    limit: int = Query(20, ge=1, le=100)  # Add query parameter with validation
):
    """Get user activities with pagination support"""
    activities = crud.get_user_activities(db, current_user.id, limit)
    return {
        "activities": activities,
        "total_count": len(activities),
        "limit": limit
    }
@router.get("/stories")
def get_user_stories_endpoint(
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100)
):
    """Get user stories with pagination and favorite status"""
    offset = (page - 1) * limit
    stories = crud.get_user_stories(db, current_user.id, limit=limit, offset=offset)
    total_count = crud.get_user_stories_count(db, current_user.id)
    
    # Add metadata including favorite status
    stories_with_metadata = []
    for story in stories:
        # Check if story is favorited
        favorite = db.query(models.StoryFavorite).filter(
            models.StoryFavorite.story_id == story.id,
            models.StoryFavorite.user_id == current_user.id
        ).first()
        
        story_dict = {
            "id": story.id,
            "title": story.title,
            "content": story.content,
            "genre": story.genre or "adventure",
            "language": story.language or "en",
            "audio_url": story.audio_url,
            "has_audio": story.has_audio or bool(story.audio_url),
            "created_at": story.created_at,
            "updated_at": story.updated_at,
            "character_count": story.character_count or len(story.content or ""),
            "word_count": story.word_count or len((story.content or "").split()),
            "reading_time": story.reading_time or max(1, len((story.content or "").split()) // 200),
            "is_favorite": bool(favorite),
        }
        stories_with_metadata.append(story_dict)
    
    total_pages = math.ceil(total_count / limit) if total_count > 0 else 1
    
    return {
        "stories": stories_with_metadata,
        "total_count": total_count,
        "current_page": page,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1
    }

@router.get("/favorite-stories")
def get_favorite_stories_endpoint(
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100)
):
    """Get user's favorite stories with pagination"""
    offset = (page - 1) * limit
    stories = crud.get_favorite_stories(db, current_user.id, limit=limit, offset=offset)
    total_count = crud.get_favorite_stories_count(db, current_user.id)

    # Format stories with metadata
    stories_with_metadata = []
    for story in stories:
        stories_with_metadata.append({
            "id": story.id,
            "title": story.title,
            "content": story.content,
            "genre": story.genre or "adventure",
            "language": story.language or "en",
            "audio_url": story.audio_url,
            "has_audio": story.has_audio or bool(story.audio_url),
            "created_at": story.created_at,
            "updated_at": story.updated_at,
            "character_count": story.character_count or len(story.content or ""),
            "word_count": story.word_count or len((story.content or "").split()),
            "reading_time": story.reading_time or max(1, len((story.content or "").split()) // 200),
            "is_favorite": True,
        })

    total_pages = math.ceil(total_count / limit) if total_count > 0 else 1
    print(stories_with_metadata)
    print(total_pages)
    return {
        "stories": stories_with_metadata,
        "total_count": total_count,
        "current_page": page,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1
    }


@router.get("/stories/{story_id}")
def get_single_story(
    story_id: int,
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get a single story by ID"""
    story = crud.get_story_by_id(db, story_id, current_user.id)
    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story not found"
        )
    
    # Check if story is favorited
    favorite = db.query(models.StoryFavorite).filter(
        models.StoryFavorite.story_id == story_id,
        models.StoryFavorite.user_id == current_user.id
    ).first()
    
    return {
        "id": story.id,
        "title": story.title,
        "content": story.content,
        "genre": story.genre or "adventure",
        "language": story.language or "en",
        "audio_url": story.audio_url,
        "has_audio": story.has_audio or bool(story.audio_url),
        "created_at": story.created_at,
        "updated_at": story.updated_at,
        "character_count": story.character_count or len(story.content or ""),
        "word_count": story.word_count or len((story.content or "").split()),
        "reading_time": story.reading_time or max(1, len((story.content or "").split()) // 200),
        "is_favorite": bool(favorite),
    }

@router.delete("/stories/{story_id}")
def delete_user_story(
    story_id: int,
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db)
):
    """Delete a user's story"""
    success = crud.delete_story(db, story_id, current_user.id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story not found"
        )
    
    # Log the activity
    crud.create_user_activity(db, current_user.id, "story_deleted", f"Deleted story (ID: {story_id})")
    
    return {"message": "Story deleted successfully"}

@router.put("/stories/{story_id}/favorite")
@router.put("/stories/{story_id}/favorite")
def toggle_story_favorite_endpoint(
    story_id: int,
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db)
):
    """Toggle story favorite status"""
    
    # Check if story exists first
    story = crud.get_story_by_id(db, story_id, current_user.id)
    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story not found"
        )
    
    # Toggle favorite status (this function already logs the activity internally)
    is_favorite = crud.toggle_story_favorite(db, story_id, current_user.id)
   
    
    return {
        "message": f"Story {'added to favorites' if is_favorite else 'removed from favorites'} successfully",
        "is_favorite": is_favorite
    }