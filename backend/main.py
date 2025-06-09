from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, status, Depends, Request, Path
from pydantic import BaseModel, EmailStr
from typing import List, Optional
from datetime import datetime, date, time, timedelta, timezone
from sqlalchemy.orm import Session
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import RedirectResponse
from googleapiclient.errors import HttpError

# Import database utilities and models
from database import SessionLocal, engine, get_db
import models
import os

# Import Google Calendar API utilities
import google_calendar_api
from google.auth.transport.requests import Request as GoogleAuthRequest

# Create database tables if they don't exist
models.create_db_tables()

load_dotenv()
# --- Configuration ---
GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID")

if not GOOGLE_CALENDAR_ID:
    raise ValueError(
        "GOOGLE_CALENDAR_ID environment variable not set. "
        "Please create a .env file or set the variable."
    )

# Initialize FastAPI app
app = FastAPI(
    title="Interview Booking API",
    description="API for booking interview slots.",
    version="0.1.0",
)

# --- CORS Configuration ---
origins = [
    "http://localhost:3000",
    "http://localhost:8000",
    # Add your Vercel deployment URL here when you have it, e.g.:
    # "https://your-frontend-app-name.vercel.app",
    # "https://*.vercel.app"  # Wildcard for all Vercel subdomains (use with caution)
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Pydantic Models for API Request/Response ---
class SlotResponse(BaseModel):
    id: str
    datetime_utc: datetime
    is_booked: bool = False

    class Config:
        from_attributes = True


class BookingRequest(BaseModel):
    # Removed slot_id, it is already a path parameter
    booked_by_name: str
    booked_by_email: EmailStr
    description: Optional[str] = None


# --- API Endpoints ---
@app.on_event("startup")
async def startup_event():
    db = SessionLocal()
    try:
        if db.query(models.Slot).count() == 0:
            _current_date = date.today()
            _start_time = time(9, 0, 0)
            _end_time = time(17, 0, 0)
            _slot_duration_minutes = 60

            generated_slots = []
            _slot_id_counter = 0

            for i in range(14):
                day = _current_date + timedelta(days=i)
                if day.weekday() < 5:
                    current_slot_time = datetime.combine(day, _start_time)
                    current_slot_time_utc = current_slot_time.astimezone(timezone.utc)
                    while current_slot_time.time() < _end_time:
                        _slot_id_counter += 1
                        slot_id = f"slot-{_slot_id_counter}"
                        generated_slots.append(
                            models.Slot(
                                id=slot_id, datetime_utc=current_slot_time_utc
                            )
                        )
                        current_slot_time += timedelta(minutes=_slot_duration_minutes)
            db.add_all(generated_slots)
            db.commit()
            print(f"Pre-populated {len(generated_slots)} slots in local DB.")

        # Check for Google Calendar credentials
        creds = google_calendar_api.get_credentials()
        if not creds or not creds.valid:
            print(
                "Google Calendar credentials not found or invalid. Please authorize the app:"
            )
            flow = google_calendar_api.get_flow()
            authorization_url, _ = flow.authorization_url(
                access_type="offline", include_granted_scopes="true"
            )
            print(f"Visit: {authorization_url}")
        elif creds and creds.expired and creds.refresh_token:
            print("Google Calendar access token expired, refreshing...")
            creds.refresh(GoogleAuthRequest())
            google_calendar_api.save_credentials(creds)
            print("Google Calendar access token refreshed.")
        else:  # Added else block for valid credentials
            print("Google Calendar credentials loaded and valid.")
    finally:
        db.close()


@app.get("/")
async def read_root():
    return {"message": "Welcome to the Interview Booking API!"}


# --- Google OAuth Endpoints ---
@app.get("/auth/google")
async def authorize_google():
    """Initiates the Google OAuth 2.0 authorization flow."""
    flow = google_calendar_api.get_flow()
    authorization_url, state = flow.authorization_url(
        access_type="offline", include_granted_scopes="true"
    )
    return RedirectResponse(authorization_url)


@app.get("/auth/google/callback")
async def google_callback(request: Request, db: Session = Depends(get_db)):
    """Handles the callback from Google after user authorization."""
    flow = google_calendar_api.get_flow()
    flow.fetch_token(authorization_response=str(request.url))

    creds = flow.credentials
    google_calendar_api.save_credentials(creds)

    return {"message": "Google Calendar authorization successful!", "token_saved": True}


@app.get("/api/slots", response_model=List[SlotResponse])
async def get_slots(
    target_date: Optional[date] = None, db: Session = Depends(get_db)
):
    """
    Retrieve available interview slots from Google Calendar and your local DB.
    """
    creds = google_calendar_api.get_credentials()
    if not creds or not creds.valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google Calendar not authorized. Please authorize the app first.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(GoogleAuthRequest())
            google_calendar_api.save_credentials(creds)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Failed to refresh Google Calendar token: {e}. Please re-authorize.",
            )

    service = google_calendar_api.build_calendar_service(creds)

    query_date = target_date if target_date else date.today()
    start_time_utc = datetime.combine(query_date, time(0, 0, 0), tzinfo=timezone.utc)
    end_time_utc = start_time_utc + timedelta(days=7)

    google_free_slots = await google_calendar_api.get_free_busy_slots(
        service,
        start_time_utc,
        end_time_utc,
        calendar_id=GOOGLE_CALENDAR_ID,  # Passing the calendar ID
    )

    available_db_slots = db.query(models.Slot).filter(
        models.Slot.is_booked == False,
        models.Slot.datetime_utc >= start_time_utc,
        models.Slot.datetime_utc < end_time_utc,
    ).order_by(models.Slot.datetime_utc).all()

    final_available_slots = []
    for db_slot in available_db_slots:
        # Make db_slot.datetime_utc timezone-aware (UTC) for comparison
        # We assume db_slot.datetime_utc is already in UTC, but currently naive
        db_slot_aware_utc = db_slot.datetime_utc.replace(tzinfo=timezone.utc)

        is_free_on_google = False
        for google_slot in google_free_slots:
            # Now both sides of the comparison are timezone-aware (UTC)
            if (
                db_slot_aware_utc >= google_slot["start"]
                and db_slot_aware_utc < google_slot["end"]
            ):
                is_free_on_google = True
                break
        if is_free_on_google:
            final_available_slots.append(db_slot)

    return final_available_slots

@app.post("/api/slots/{slot_id}/book", response_model=SlotResponse, status_code=status.HTTP_200_OK)
async def book_slot(
    booking_details: BookingRequest, # NO DEFAULT - MUST COME FIRST
    slot_id: str = Path(..., description="The ID of the slot to book"),
    db: Session = Depends(get_db),
):
    """
    Books an available slot in the local database and creates a Google Calendar event.
    """
    # 1. Get Google Calendar Credentials
    creds = google_calendar_api.get_credentials()
    if not creds or not creds.valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google Calendar not authorized. Please authorize the app first.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(GoogleAuthRequest())
            google_calendar_api.save_credentials(creds)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Failed to refresh Google Calendar token: {e}. Please re-authorize.",
            )

    service = google_calendar_api.build_calendar_service(creds)

    # 2. Find the slot in the local database
    slot = db.query(models.Slot).filter(models.Slot.id == slot_id).first()
    if not slot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Slot not found")

    # 3. Check if the slot is already booked locally
    if slot.is_booked:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Slot is already booked."
        )

    # 4. Create Google Calendar event
    try:
        # Ensure the datetime from DB is timezone-aware (UTC) for Google Calendar API
        slot_datetime_aware_utc = slot.datetime_utc.replace(tzinfo=timezone.utc)
        # Assuming slots are 1 hour long. Adjust if your slots are different.
        event_end_time_utc = slot_datetime_aware_utc + timedelta(hours=1)

        await google_calendar_api.create_calendar_event(
            service,
            slot_datetime_aware_utc,
            event_end_time_utc,
            booking_details.booked_by_name,  # Use booked_by_name for summary
            booking_details.description,     # This will now exist
            booking_details.booked_by_email,
            GOOGLE_CALENDAR_ID,
        )

    except HttpError as e:
        print(f"Google Calendar API Error during event creation: {e.content.decode()}")
        raise HTTPException(
            status_code=e.resp.status, detail=f"Google Calendar API Error: {e.content.decode()}"
        )
    except Exception as e:
        print(f"Unexpected error during event creation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create calendar event due to an unexpected error: {e}",
        )

    # 5. If Google Calendar event created successfully, mark slot as booked in local DB
    slot.is_booked = True
    db.add(slot)
    db.commit()
    db.refresh(slot)

    return slot