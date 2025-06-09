# booking-backend/main.py

from fastapi import FastAPI, HTTPException, status, Path # <-- IMPORT Path here!
from pydantic import BaseModel
from typing import List, Optional
# Ensure timezone is imported for proper UTC handling
from datetime import datetime, date, time, timedelta, timezone # <-- Added timezone
from fastapi.middleware.cors import CORSMiddleware
# For Google Calendar API integration
import os # Make sure os is imported for environment variables
from google.auth.transport.requests import Request as GoogleAuthRequest # Rename Request to avoid conflict
from googleapiclient.errors import HttpError

# Assuming these are in a separate file like google_calendar_api.py
# If not, you'll need to include their definitions here or import them correctly.
import google_calendar_api # Assuming your functions are in this module
from dotenv import load_dotenv

load_dotenv() # Load environment variables from .env file

# --- Configuration for Google Calendar ---
# You need to define GOOGLE_CALENDAR_ID (usually your primary calendar email)
# It's good practice to get this from environment variables
GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "primary") 
# If 'primary' is not working or you have a specific calendar, use its ID or email.
if not GOOGLE_CALENDAR_ID:
    print("WARNING: GOOGLE_CALENDAR_ID environment variable not set. Defaulting to 'primary'.")


# Initialize FastAPI app
app = FastAPI(
    title="Interview Booking API",
    description="API for booking interview slots.",
    version="0.1.0",
)

# --- CORS Configuration ---
origins = [
    "http://localhost:3000",  # Your Next.js frontend development server
    "http://localhost:8000",  # Or whatever port your frontend runs on
    # Add your Vercel deployment URL here when you have it, e.g.:
    # "https://your-frontend-app-name.vercel.app",
    # "https://*.vercel.app" # Wildcard for all Vercel subdomains (use with caution)
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- In-Memory Database (for demonstration) ---
class SlotInDB(BaseModel):
    id: str
    datetime_utc: datetime  # Store as UTC to handle time zones
    is_booked: bool = False
    booked_by_name: Optional[str] = None
    booked_by_email: Optional[str] = None
    description: Optional[str] = None # Added description field for booking details

# Generate some initial slots for testing
_current_date = date.today()
_start_time = time(9, 0, 0) # 9 AM
_end_time = time(17, 0, 0)  # 5 PM (end exclusive, so slots up to 4 PM)
_slot_duration_minutes = 60 # 1 hour slots

_available_slots: List[SlotInDB] = []
_slot_id_counter = 0

# Generate slots for the next 7 days (Monday to Friday only)
for i in range(7):
    day = _current_date + timedelta(days=i)
    if day.weekday() < 5:  # 0=Monday, 4=Friday
        # --- IMPORTANT: Make the datetime_utc explicitly UTC-aware ---
        current_slot_time = datetime.combine(day, _start_time, tzinfo=timezone.utc) # <-- Applied timezone.utc
        
        while current_slot_time.time() < _end_time:
            _slot_id_counter += 1
            slot_id = f"slot-{_slot_id_counter}"
            _available_slots.append(
                SlotInDB(
                    id=slot_id,
                    datetime_utc=current_slot_time
                )
            )
            current_slot_time += timedelta(minutes=_slot_duration_minutes)


# --- Pydantic Models for API Request/Response ---
class SlotResponse(BaseModel):
    id: str
    datetime_utc: datetime

    class Config:
        from_attributes = True


class BookingRequest(BaseModel):
    # slot_id: str # No longer needed here, as it's a Path parameter
    booked_by_name: str
    booked_by_email: str
    description: Optional[str] = None # Added description to the request model


# --- API Endpoints ---

@app.get("/")
async def read_root():
    return {"message": "Welcome to the Interview Booking API!"}


@app.get("/api/slots", response_model=List[SlotResponse])
async def get_slots(target_date: Optional[date] = None):
    """
    Retrieve available interview slots for a given date.
    If no date is provided, returns all available slots (from in-memory demo).
    """
    if target_date:
        filtered_slots = [
            slot for slot in _available_slots
            if not slot.is_booked and slot.datetime_utc.date() == target_date
        ]
    else:
        filtered_slots = [slot for slot in _available_slots if not slot.is_booked]

    filtered_slots.sort(key=lambda s: s.datetime_utc)
    return filtered_slots


@app.post("/api/slots/{slot_id}/book", response_model=SlotResponse, status_code=status.HTTP_200_OK)
async def book_slot(
    slot_id: str = Path(..., description="The ID of the slot to book"), # slot_id as Path parameter
    booking_details: BookingRequest = None # Booking details from request body
):
    """
    Books an available slot in the local in-memory database and creates a Google Calendar event.
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
            creds.refresh(GoogleAuthRequest()) # <-- Using GoogleAuthRequest as aliased
            google_calendar_api.save_credentials(creds)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Failed to refresh Google Calendar token: {e}. Please re-authorize.",
            )

    service = google_calendar_api.build_calendar_service(creds)

    # 2. Find the slot in the local in-memory database
    slot_found = None
    for slot in _available_slots:
        if slot.id == slot_id:
            slot_found = slot
            break

    if not slot_found:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Slot not found")

    # 3. Check if the slot is already booked locally
    if slot_found.is_booked:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Slot is already booked."
        )

    # 4. Create Google Calendar event
    try:
        # Ensure the datetime from DB is timezone-aware (UTC) for Google Calendar API
        # It should already be UTC from our generation logic
        slot_datetime_aware_utc = slot_found.datetime_utc.replace(tzinfo=timezone.utc)
        # Assuming slots are 1 hour long.
        event_end_time_utc = slot_datetime_aware_utc + timedelta(hours=1)

        await google_calendar_api.create_calendar_event(
            service,
            slot_datetime_aware_utc,
            event_end_time_utc,
            booking_details.booked_by_name,
            booking_details.description, # This is now passed from the request
            booking_details.booked_by_email,
            GOOGLE_CALENDAR_ID, # <-- Defined at the top
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

    # 5. If Google Calendar event created successfully, mark slot as booked in local in-memory DB
    slot_found.is_booked = True
    slot_found.booked_by_name = booking_details.booked_by_name
    slot_found.booked_by_email = booking_details.booked_by_email
    slot_found.description = booking_details.description # Store description

    return slot_found # Return the updated slot