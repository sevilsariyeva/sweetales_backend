import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.database import engine, get_db
from app import models
from app.routers import auth, story, payment, user

# Create database tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Story Generator API", version="2.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Static files
if not os.path.exists("static"):
    os.makedirs("static")
app.mount("/static", StaticFiles(directory="static"), name="static")

if not os.path.exists("uploads"):
    os.makedirs("uploads")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
# Include routers
app.include_router(auth.router)
app.include_router(story.router)
app.include_router(payment.router)
app.include_router(user.router)

@app.get("/")
async def root():
    return {
        "message": "Story Generator API v2.0 is running",
        "version": "2.0",
        "features": [
            "User authentication",
            "Credit system", 
            "Story generation with AI",
            "Audio synthesis",
            "Payment processing"
        ],
        "endpoints": {
            "auth": {
                "register": "/auth/register",
                "login": "/auth/login",
                "me": "/auth/me"
            },
            "story": {
                "generate": "/api/generate-story",
                "audio": "/api/audio/{file_name}",
                "my_stories": "/api/my-stories"
            },
            "payment": {
                "plans": "/payment/plans",
                "create_intent": "/payment/create-payment-intent",
                "confirm": "/payment/confirm-payment",
                "transactions": "/payment/transactions"
            },
            "user": {
                "profile": "/user/profile",
                "credits": "/user/credits",
                "dashboard": "/user/dashboard"
            }
        }
    }

@app.get("/health")
async def health_check():
    try:
        # Test database connection
        db = next(get_db())
        db.execute(text("SELECT 1"))
        db_status = "OK"
    except Exception as e:
        db_status = f"ERROR: {str(e)}"
    
    return {
        "status": "OK",
        "database": db_status,
        "version": "2.0"
    }

# Initialize default plans
@app.on_event("startup")
async def startup_event():
    from app.database import SessionLocal
    from app import crud, schemas
    
    db = SessionLocal()
    try:
        # Check if plans exist
        existing_plans = crud.get_plans(db)
        if not existing_plans:
            # Create default plans
            plans = [
                {"name": "Basic", "credits": 400, "price": 9.0},
                {"name": "Standard", "credits": 1000, "price": 19.0}, 
                {"name": "Premium", "credits": 2000, "price": 39.0},
                {"name": "Ultimate", "credits": 5000, "price": 79.0}
            ]
            
            for plan_data in plans:
                plan = schemas.PlanCreate(**plan_data)
                crud.create_plan(db, plan)
                
            print("Default plans created!")
    except Exception as e:
        print(f"Error creating default plans: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")