from fastapi import APIRouter, Depends, HTTPException, Request, Header
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from decouple import config
import stripe

from .. import crud, models, schemas, auth
from ..database import get_db

router = APIRouter(prefix="/payment", tags=["payment"])

stripe.api_key = config("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = config("STRIPE_WEBHOOK_SECRET", default="")
FRONTEND_URL = config("FRONTEND_URL", default="http://localhost:3000")


# ── Get all plans ─────────────────────────────────────────────────────────────
@router.get("/plans")
def get_plans(db: Session = Depends(get_db)):
    plans = crud.get_plans(db)
    return [
        {
            "id": p.id,
            "name": p.name,
            "credits": p.credits,
            "price": p.price,
            "popular": p.popular,
            "description": p.description,
        }
        for p in plans
    ]


# ── Create Stripe Checkout Session ───────────────────────────────────────────
@router.post("/create-checkout-session")
def create_checkout_session(
    data: schemas.TransactionCreate,
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    plan = crud.get_plan(db, data.plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    try:
        # Create Stripe Checkout Session
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "product_data": {
                            "name": f"{plan.name} — {plan.credits} Credits",
                            "description": plan.description or f"Purchase {plan.credits} credits for Sweet Tales",
                        },
                        "unit_amount": int(plan.price * 100),  # cents
                    },
                    "quantity": 1,
                }
            ],
            mode="payment",
            success_url=f"{FRONTEND_URL}/buy-credits/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{FRONTEND_URL}/buy-credits?cancelled=true",
            metadata={
                "user_id": str(current_user.id),
                "plan_id": str(plan.id),
                "credits": str(plan.credits),
            },
            customer_email=current_user.email,
        )

        # Save pending transaction
        transaction = crud.create_transaction(
            db,
            user_id=current_user.id,
            plan_id=plan.id,
            amount=plan.price,
            credits=plan.credits,
            status="pending",
        )
        # Store stripe session id
        transaction.stripe_session_id = session.id
        db.commit()

        return {"session_id": session.id, "url": session.url, "transaction_id": transaction.id}

    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Verify payment after redirect ────────────────────────────────────────────
@router.get("/verify/{session_id}")
def verify_payment(
    session_id: str,
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    try:
        session = stripe.checkout.Session.retrieve(session_id)

        if session.payment_status != "paid":
            return {"status": "pending", "message": "Payment not completed yet"}

        # Check if already processed
        from ..models import Transaction
        tx = db.query(Transaction).filter(
            Transaction.stripe_session_id == session_id,
            Transaction.user_id == current_user.id,
        ).first()

        if tx and tx.status == "completed":
            return {
                "status": "already_processed",
                "credits": current_user.credits,
                "message": "Payment already processed",
            }

        if tx:
            # Add credits
            credits = int(session.metadata.get("credits", 0))
            crud.update_user_credits(db, current_user.id, credits)
            crud.update_transaction_status(db, tx.id, "completed", session.payment_intent)
            crud.create_user_activity(
                db, current_user.id, "credits_purchased",
                f"Purchased {credits} credits for ${tx.amount}"
            )
            db.refresh(current_user)
            return {
                "status": "success",
                "credits_added": credits,
                "credits": current_user.credits,
                "message": f"Successfully added {credits} credits!",
            }

        return {"status": "error", "message": "Transaction not found"}

    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Stripe Webhook ────────────────────────────────────────────────────────────
@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="stripe-signature"),
    db: Session = Depends(get_db),
):
    payload = await request.body()

    if not STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=400, detail="Webhook secret not configured")

    try:
        event = stripe.Webhook.construct_event(payload, stripe_signature, STRIPE_WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        if session.get("payment_status") != "paid":
            return {"status": "skipped"}

        user_id = int(session["metadata"].get("user_id", 0))
        plan_id = int(session["metadata"].get("plan_id", 0))
        credits = int(session["metadata"].get("credits", 0))

        from ..models import Transaction
        tx = db.query(Transaction).filter(
            Transaction.stripe_session_id == session["id"]
        ).first()

        if tx and tx.status != "completed":
            crud.update_user_credits(db, user_id, credits)
            crud.update_transaction_status(db, tx.id, "completed", session.get("payment_intent"))
            crud.create_user_activity(
                db, user_id, "credits_purchased",
                f"Purchased {credits} credits via Stripe"
            )

    return {"status": "ok"}


# ── Transaction history ───────────────────────────────────────────────────────
@router.get("/transactions")
def get_transactions(
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    txs = crud.get_user_transactions(db, current_user.id, limit=20)
    return [
        {
            "id": t.id,
            "amount": t.amount,
            "credits_purchased": t.credits_purchased,
            "status": t.status,
            "created_at": t.created_at,
            "plan_id": t.plan_id,
        }
        for t in txs
    ]