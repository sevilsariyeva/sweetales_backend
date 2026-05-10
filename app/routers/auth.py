import os
import urllib.parse
import httpx
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from decouple import config
from .. import crud, models, schemas, auth
from ..database import get_db

router = APIRouter(prefix="/auth", tags=["auth"])

GOOGLE_CLIENT_ID     = config("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = config("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI  = config("GOOGLE_REDIRECT_URI", default="http://localhost:8000/auth/google/callback")
FRONTEND_URL         = config("FRONTEND_URL", default="http://localhost:3000")

GOOGLE_AUTH_URL  = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USER_URL  = "https://www.googleapis.com/oauth2/v2/userinfo"


# ── Classic register / login ──────────────────────────────────────────────────

@router.post("/register", response_model=schemas.Token)
def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
    if crud.get_user_by_email(db, user.email):
        raise HTTPException(status_code=400, detail="Email already registered")
    if crud.get_user_by_username(db, user.username):
        raise HTTPException(status_code=400, detail="Username already taken")
    db_user = crud.create_user(db, user)
    access_token = auth.create_access_token(
        data={"sub": db_user.email},
        expires_delta=timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/login", response_model=schemas.Token)
def login(user_data: schemas.UserLogin, db: Session = Depends(get_db)):
    user = auth.authenticate_user(db, user_data.email, user_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = auth.create_access_token(
        data={"sub": user.email},
        expires_delta=timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=schemas.User)
def get_me(current_user: models.User = Depends(auth.get_current_active_user)):
    return current_user


# ── Google OAuth2 ─────────────────────────────────────────────────────────────

@router.get("/google")
def google_login():
    params = {
        "client_id":     GOOGLE_CLIENT_ID,
        "redirect_uri":  GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope":         "openid email profile",
        "access_type":   "offline",
        "prompt":        "select_account",
    }
    query = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
    return RedirectResponse(url=f"{GOOGLE_AUTH_URL}?{query}")


@router.get("/google/callback")
async def google_callback(code: str, db: Session = Depends(get_db)):
    # 1. code → access_token
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code":          code,
                "client_id":     GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri":  GOOGLE_REDIRECT_URI,
                "grant_type":    "authorization_code",
            },
        )

    if token_resp.status_code != 200:
        raise HTTPException(status_code=400, detail="Google token exchange failed")

    google_token = token_resp.json().get("access_token")

    # 2. access_token → user info
    async with httpx.AsyncClient() as client:
        user_resp = await client.get(
            GOOGLE_USER_URL,
            headers={"Authorization": f"Bearer {google_token}"},
        )

    if user_resp.status_code != 200:
        raise HTTPException(status_code=400, detail="Failed to fetch Google user info")

    google_user = user_resp.json()
    email   = google_user.get("email", "")
    name    = google_user.get("name", "")
    picture = google_user.get("picture", "")

    if not email:
        raise HTTPException(status_code=400, detail="Google account has no email")

    # 3. İstifadəçi var mı?
    db_user = crud.get_user_by_email(db, email)

    if not db_user:
        username = name.replace(" ", "_").lower() or email.split("@")[0]
        base, counter = username, 1
        while crud.get_user_by_username(db, username):
            username = f"{base}{counter}"
            counter += 1

        new_user = schemas.UserCreate(
            email=email,
            username=username,
            password=os.urandom(32).hex(),
        )
        db_user = crud.create_user(db, new_user)
        if picture:
            crud.update_user_avatar(db, db_user.id, picture)

    # 4. JWT yarat
    access_token = auth.create_access_token(
        data={"sub": db_user.email},
        expires_delta=timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    # 5. Frontend callback-ə token + user məlumatları ilə yönləndir
    params = urllib.parse.urlencode({
        "token":   access_token,
        "name":    name,
        "email":   email,
        "picture": picture,
    })
    return RedirectResponse(
        url=f"{FRONTEND_URL}/auth/callback?{params}",
        status_code=302,
    )


@router.post("/change-password")
def change_password(
    data: schemas.PasswordChange,
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    if not auth.verify_password(data.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    auth.update_user_password(db, current_user.id, data.new_password)
    return {"message": "Password changed successfully"}