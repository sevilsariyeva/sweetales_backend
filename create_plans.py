from app.database import SessionLocal
from app import crud, schemas, models

def create_default_plans():
    db = SessionLocal()
    try:
        # Default plans
        plans_data = [
            {"name": "Starter", "credits": 400, "price": 9.0},
            {"name": "Popular", "credits": 1000, "price": 19.0}, 
            {"name": "Premium", "credits": 2000, "price": 39.0},
            {"name": "Ultimate", "credits": 5000, "price": 79.0}
        ]
        
        for plan_data in plans_data:
            # Check if plan exists
            existing = db.query(models.Plan).filter(models.Plan.name == plan_data["name"]).first()
            if not existing:
                plan = schemas.PlanCreate(**plan_data)
                crud.create_plan(db, plan)
                print(f"Plan '{plan_data['name']}' created!")
            else:
                print(f"Plan '{plan_data['name']}' already exists")
                
    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    create_default_plans()