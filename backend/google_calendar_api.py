# booking-backend/google_calendar_api.py

import os
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1" # Keep this for local dev!

from datetime import datetime, timedelta, timezone
from google.auth.transport.requests import Request # Note: Renamed to GoogleAuthRequest in main.py
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import json
from dotenv import load_dotenv

load_dotenv()

# --- Configuration ---
CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")

if not CLIENT_ID or not CLIENT_SECRET:
    raise ValueError("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET environment variables must be set.")

SCOPES = ["https://www.googleapis.com/auth/calendar"]
REDIRECT_URI = "http://localhost:8000/auth/google/callback"
TOKEN_FILE = "token.json"

def get_flow():
    """Initializes and returns the Google OAuth flow."""
    # Ensure client_secret.json exists, even if values come from .env
    # The 'web' key is expected by Flow.from_client_secrets_file
    client_config = {
        "web": {
            "client_id": CLIENT_ID,
            "project_id": "your-project-id", # Placeholder, not strictly used by flow but needed for structure
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_secret": CLIENT_SECRET,
            "redirect_uris": [REDIRECT_URI],
            "javascript_origins": ["http://localhost:3000"] # Add your frontend origin if applicable
        }
    }
    # Temporarily write to a dummy file to satisfy Flow.from_client_secrets_file
    # In a real app, you'd use Flow.from_client_config directly.
    temp_client_secret_path = "temp_client_secret_flow.json"
    with open(temp_client_secret_path, "w") as f:
        json.dump(client_config, f)

    flow = Flow.from_client_secrets_file(
        temp_client_secret_path,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )
    os.remove(temp_client_secret_path) # Clean up the temporary file
    return flow

def save_credentials(creds):
    """Saves the credentials to a file."""
    with open(TOKEN_FILE, "w") as token:
        token.write(creds.to_json())
    print("Credentials saved to token.json")

def get_credentials():
    """Loads credentials from a file, or returns None if not found."""
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    return creds

def build_calendar_service(creds):
    """Builds and returns a Google Calendar API service object."""
    try:
        service = build("calendar", "v3", credentials=creds)
        return service
    except Exception as e:
        print(f"Error building calendar service: {e}")
        return None

# The get_free_busy_slots and create_calendar_event functions as provided previously
# ... (rest of your get_free_busy_slots and create_calendar_event functions) ...

async def get_free_busy_slots(service, start_time: datetime, end_time: datetime, calendar_id: str = 'primary'):
    """
    Queries Google Calendar for free/busy information for a specific calendar.

    Args:
        service: An authorized Google Calendar API service object.
        start_time: The start of the time range to query (datetime object, UTC).
        end_time: The end of the time range to query (datetime object, UTC).
        calendar_id: The ID of the calendar to query (e.g., 'primary' or an email address).
    Returns:
        A list of dictionaries, where each dictionary represents a free slot
        with 'start' and 'end' datetime objects (UTC).
    """
    try:
        body = {
            "timeMin": start_time.isoformat(),
            "timeMax": end_time.isoformat(),
            "items": [{"id": calendar_id}] # Use the passed calendar_id
        }
        free_busy_query_result = service.freebusy().query(body=body).execute()

        busy_periods = free_busy_query_result['calendars'][calendar_id]['busy']

        free_slots = []
        current_time = start_time
        while current_time < end_time:
            is_busy = False
            for busy_period in busy_periods:
                busy_start = datetime.fromisoformat(busy_period['start'])
                busy_end = datetime.fromisoformat(busy_period['end'])
                if current_time >= busy_start and current_time < busy_end:
                    is_busy = True
                    break
            
            if not is_busy:
                free_slots.append({
                    'start': current_time,
                    'end': current_time + timedelta(hours=1) # Assuming 1-hour slots
                })
            
            current_time += timedelta(hours=1)

        return free_slots

    except HttpError as error:
        print(f"An error occurred: {error}")
        return []
    except Exception as e:
        print(f"An unexpected error occurred in get_free_busy_slots: {e}")
        return []


async def create_calendar_event(service, start_time: datetime, end_time: datetime,
                                summary: str, description: str, attendee_email: str,
                                calendar_id: str = 'primary'): # Add calendar_id parameter
    """
    Creates a new event on the specified Google Calendar.

    Args:
        service: An authorized Google Calendar API service object.
        start_time: The start time of the event (datetime object, UTC).
        end_time: The end time of the event (datetime object, UTC).
        summary: The event's title.
        description: A detailed description of the event.
        attendee_email: The email address of the attendee.
        calendar_id: The ID of the calendar to create the event on (e.g., 'primary' or an email address).
    Returns:
        The created event resource.
    """
    event = {
        'summary': summary,
        'description': description,
        'start': {
            'dateTime': start_time.isoformat(),
            'timeZone': 'UTC',
        },
        'end': {
            'dateTime': end_time.isoformat(),
            'timeZone': 'UTC',
        },
        'attendees': [
            {'email': attendee_email},
            {'email': calendar_id}, # The calendar owner is also an attendee
        ],
        'reminders': {
            'useDefault': False,
            'overrides': [
                {'method': 'email', 'minutes': 24 * 60},
                {'method': 'popup', 'minutes': 10},
            ],
        },
        'conferenceData': {
            'createRequest': {
                'requestId': f"booking-{start_time.strftime('%Y%m%d%H%M%S')}-{os.urandom(8).hex()}",
                'conferenceSolutionKey': {'type': 'hangoutsMeet'}
            }
        }
    }

    try:
        event = service.events().insert(calendarId=calendar_id, body=event, conferenceDataVersion=1).execute()
        print(f"Event created: {event.get('htmlLink')}")
        return event
    except HttpError as error:
        print(f"An error occurred while creating event: {error}")
        raise
    except Exception as e:
        print(f"An unexpected error occurred in create_calendar_event: {e}")
        raise