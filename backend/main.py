# booking-backend/main.py

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
from google.auth.transport.requests import Request as GoogleAuthRequest # Correct alias usage

# Create database tables if they don't exist
models.create_db_tables()

load_dotenv()
# --- Configuration ---
GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID")
SLOT_DURATION_HOURS = int(os.getenv("SLOT_DURATION_HOURS", "1"))
# --- Define your business rules for slot generation ---
# Assuming your local timezone is CEST (UTC+2) for these hours
LOCAL_BUSINESS_START_HOUR = 9  # 9 AM local time (e.g., 9:00 AM CEST)
LOCAL_BUSINESS_END_HOUR = 17   # 5 PM local time (e.g., 5:00 PM CEST)
DAYS_TO_LOOK_AHEAD = 7         # Look for slots over the next 7 days

# Convert local business hours to their UTC equivalents for internal logic
# (e.g., 9:00 AM CEST is 7:00 AM UTC; 5:00 PM CEST is 3:00 PM UTC)
UTC_BUSINESS_START_HOUR = LOCAL_BUSINESS_START_HOUR - 2 # Adjust based on your local offset
UTC_BUSINESS_END_HOUR = LOCAL_BUSINESS_END_HOUR - 2     # Adjust based on your local offset


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
    "https://booking-six-ecru.vercel.app/",
    "https://booking-backend-o38g.onrender.com/",
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
    booked_by_name: Optional[str] = None # Added for clarity in response
    booked_by_email: Optional[EmailStr] = None # Added for clarity in response
    description: Optional[str] = None # Added for clarity in response

    class Config:
        from_attributes = True


class BookingRequest(BaseModel):
    booked_by_name: str
    booked_by_email: EmailStr
    description: Optional[str] = None


# --- API Endpoints ---

# The @app.on_event("startup") will no longer pre-populate generic slots.
# It will now only check for Google Calendar credentials.
@app.on_event("startup")
async def startup_event():
    db = SessionLocal()
    try:
        # Check for Google Calendar credentials
        creds = google_calendar_api.get_credentials()

        # --- Start Custom Validity and Expiry Check ---
        # This replaces the problematic `creds.valid` and `creds.expired` properties.
        # We assume get_credentials has already ensured creds.expiry is timezone-aware if it exists.
        
        is_creds_valid_custom = False
        if creds and creds.token: # Ensure creds object and an access token string exist
            if creds.expiry is None: # If expiry is unexpectedly None, it's not valid
                is_creds_valid_custom = False
            else:
                current_utc_time = datetime.now(timezone.utc)
                if creds.expiry > current_utc_time: # Check if expiry is in the future
                    is_creds_valid_custom = True
                # else: is_creds_valid_custom remains False (expired)
        
        # Now, use our custom flag for conditional logic
        if not is_creds_valid_custom:
            print("Google Calendar credentials not found or invalid. Please authorize the app:")
            flow = google_calendar_api.get_flow()
            authorization_url, _ = flow.authorization_url(
                access_type="offline", include_granted_scopes="true"
            )
            print(f"Visit: {authorization_url}")
        
        # We don't need a separate `elif creds and creds.expired and creds.refresh_token:`
        # because `get_credentials()` already handles the refresh if it was triggered
        # by an actual expiration. If `get_credentials()` returned a valid token
        # (meaning `is_creds_valid_custom` is True), then it's already refreshed if needed.
        else: # This means is_creds_valid_custom is True
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
    Retrieve available interview slots by dynamically generating potential slots
    based on business hours and checking real-time availability with Google Calendar.
    """
    creds = google_calendar_api.get_credentials()
    if not creds:
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

    # Determine the date range for the query
    query_date = target_date if target_date else date.today()
    
    # --- Generate all potential slots based on your defined business rules ---
    potential_bookable_slots_utc: List[datetime] = []
    for i in range(DAYS_TO_LOOK_AHEAD):
        current_day = query_date + timedelta(days=i)
        # Exclude weekends (Monday=0, Sunday=6)
        if current_day.weekday() < 5: # This means Mon-Fri
            current_slot_time_utc = datetime.combine(current_day, time(UTC_BUSINESS_START_HOUR, 0, 0), tzinfo=timezone.utc)
            while current_slot_time_utc.hour < UTC_BUSINESS_END_HOUR:
                potential_bookable_slots_utc.append(current_slot_time_utc)
                current_slot_time_utc += timedelta(hours=SLOT_DURATION_HOURS)

    # --- Query Google Calendar for busy periods within the entire range ---
    # The range should cover all potential slots you just generated
    gcal_query_start_utc = datetime.combine(query_date, time(UTC_BUSINESS_START_HOUR, 0, 0), tzinfo=timezone.utc)
    gcal_query_end_utc = datetime.combine(query_date + timedelta(days=DAYS_TO_LOOK_AHEAD), time(UTC_BUSINESS_END_HOUR, 0, 0), tzinfo=timezone.utc)
    
    google_free_slots = await google_calendar_api.get_free_busy_slots(
        service,
        gcal_query_start_utc,
        gcal_query_end_utc,
        calendar_id=GOOGLE_CALENDAR_ID,
    )
    # print(f"Google free slots: {google_free_slots}") # For debugging

    # --- Get locally booked slots from your database ---
    # These are slots that were previously "available" but are now marked as booked locally.
    # Note: If a slot is booked locally, it *should* also be booked on Google Calendar.
    # This query acts as an additional layer of truth/confirmation.
    locally_booked_slots = db.query(models.Slot).filter(
        models.Slot.is_booked == True,
        models.Slot.datetime_utc >= gcal_query_start_utc, # Filter by the same date range
        models.Slot.datetime_utc < gcal_query_end_utc,
    ).all()

    # Create a set of locally booked slot start times for efficient lookup
    locally_booked_start_times_utc = {slot.datetime_utc.replace(tzinfo=timezone.utc) for slot in locally_booked_slots}

    # --- Determine the final list of truly available slots ---
    final_available_slots: List[SlotResponse] = []
    
    # Convert google_free_slots into a set of their start times for efficient lookup
    google_free_start_times = {slot["start"] for slot in google_free_slots}

    for potential_slot_start_utc in potential_bookable_slots_utc:
        # A slot is truly available if:
        # 1. It's within your business hours (already ensured by potential_bookable_slots_utc)
        # 2. Google Calendar marks it as free
        # 3. It's not marked as booked in your local database
        if (potential_slot_start_utc in google_free_start_times) and \
           (potential_slot_start_utc not in locally_booked_start_times_utc):
            
            # Generate a temporary ID for the response, as it's not from a static DB entry
            slot_id = f"dynamic-{potential_slot_start_utc.strftime('%Y%m%d%H%M%S')}-UTC"
            
            final_available_slots.append(
                SlotResponse(
                    id=slot_id,
                    datetime_utc=potential_slot_start_utc,
                    is_booked=False, # By definition, this is an available slot
                    booked_by_name=None,
                    booked_by_email=None,
                    description=None
                )
            )

    # Sort the final slots for consistent display
    final_available_slots.sort(key=lambda s: s.datetime_utc)

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
    if not creds:
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

    # 2. Check if the slot is already booked locally (if it exists in DB)
    # The slot_id here will be dynamic-YYYYMMDDHHMMSS-UTC generated by get_slots
    # So we need to parse its datetime_utc from the ID to find it in the DB.
    try:
        # Extract datetime from the ID format "dynamic-YYYYMMDDHHMMSS-UTC"
        dt_str = slot_id.split('-')[1] # YYYYMMDDHHMMSS
        slot_datetime_utc_from_id = datetime.strptime(dt_str, '%Y%m%d%H%M%S').replace(tzinfo=timezone.utc)
    except IndexError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid slot ID format.")
    
    # Try to find the slot in the DB based on its datetime_utc
    slot = db.query(models.Slot).filter(models.Slot.datetime_utc == slot_datetime_utc_from_id).first()

    # IMPORTANT: Now, booking a slot means *creating* a new entry in your local DB
    # if it doesn't exist, and then marking it as booked.
    if slot:
        if slot.is_booked:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Slot is already booked."
            )
        # If it exists and is not booked, we'll use this existing slot.
    else:
        # If the slot doesn't exist in the DB, it means it's a new booking.
        # Create a new slot entry in the DB.
        slot = models.Slot(
            id=slot_id, # Use the dynamic ID passed from the frontend
            datetime_utc=slot_datetime_utc_from_id,
            is_booked=False # Will be set to True after GCal success
        )
        db.add(slot)
        db.commit() # Commit to get an ID if SQLAlchemy generates one, or just to make it available
        db.refresh(slot) # Refresh to load any generated fields like ID if applicable

    # 3. Double-check availability with Google Calendar *right before booking*
    # This is a crucial step to prevent double-bookings if GCal status changed quickly.
    slot_start_time_utc = slot_datetime_utc_from_id
    slot_end_time_utc = slot_start_time_utc + timedelta(hours=SLOT_DURATION_HOURS) # Assuming 1-hour slots as per get_slots

    # Query just this specific slot's time range on Google Calendar
    check_free_slots = await google_calendar_api.get_free_busy_slots(
        service,
        slot_start_time_utc,
        slot_end_time_utc,
        calendar_id=GOOGLE_CALENDAR_ID
    )
    # If this specific slot start time is NOT in the list of free slots, it's busy
    if slot_start_time_utc not in {s['start'] for s in check_free_slots}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Slot is no longer available on Google Calendar.")


    # 4. Create Google Calendar event
    try:
        # Assuming slots are 1 hour long. Adjust if your slots are different.
        event_end_time_utc = slot_start_time_utc + timedelta(hours=SLOT_DURATION_HOURS)

        created_event = await google_calendar_api.create_calendar_event(
            service,
            slot_start_time_utc,
            event_end_time_utc,
            f"Interview: {booking_details.booked_by_name}", # Summary for GCal
            booking_details.description or "Interview booking", # Description for GCal
            booking_details.booked_by_email,
            GOOGLE_CALENDAR_ID,
        )
        # You might want to store created_event.get('htmlLink') or event_id in your DB slot for reference
        slot.google_event_id = created_event.get('id') # Assuming you add this column to models.Slot
        # If you need to handle potential 'calendar_id' in a more complex way for other calendars,
        # ensure it's either hardcoded or configured appropriately.

    except HttpError as e:
        print(f"Google Calendar API Error during event creation: {e.content.decode()}")
        # If Google Calendar API rejects, we shouldn't mark as booked locally
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
    slot.booked_by_name = booking_details.booked_by_name
    slot.booked_by_email = booking_details.booked_by_email
    slot.description = booking_details.description
    
    db.add(slot)
    db.commit()
    db.refresh(slot)

    return slot