# booking-backend/google_calendar_api.py

import os
from datetime import datetime, timedelta, timezone
import json

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from dotenv import load_dotenv

os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"  # Keep this for local dev!

load_dotenv()

# --- Configuration ---
CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID")  # Default to primary calendar if not set

if not CLIENT_ID or not CLIENT_SECRET:
    raise ValueError("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET environment variables must be set.")

SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.freebusy"
]
REDIRECT_URI = os.getenv("REDIRECT_URI", "http://localhost:8000/auth/google/callback") # Use env var, with fallback
PROJECT_ID = os.getenv("GOOGLE_PROJECT_ID", "your-default-project-id") # Fallback for project_id
# TOKEN_FILE = "token.json"
ACT_TOKEN_FILE = "/etc/secrets/token.json"
TOKEN_FILE = "token.json"
# ./etc/secrets/


def get_flow():
    """Initializes and returns the Google OAuth flow."""
    client_config = {
        "web": {
            "client_id": CLIENT_ID,
            "project_id": PROJECT_ID,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_secret": CLIENT_SECRET,
            "redirect_uris": [REDIRECT_URI],
            "javascript_origins": ["http://localhost:3000"]
        }
    }
    # Removed temporary file creation for client_config
    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )
    return flow


def save_credentials(creds: Credentials):
    """
    Saves the credentials to token.json, preserving existing fields
    and only updating the fields present in the new credentials object.
    """
    # Convert new credentials to a dictionary representation
    new_creds_data = json.loads(creds.to_json())

    existing_data = {}
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, "r") as f:
                existing_data = json.load(f)
            print(f"DEBUG: Existing token.json data loaded: {existing_data.keys()}")
        except json.JSONDecodeError:
            print(f"WARNING: Could not decode existing {TOKEN_FILE}. Creating new one.")
            existing_data = {}
        except Exception as e:
            print(f"ERROR: Failed to read {TOKEN_FILE}: {e}. Creating new one.")
            existing_data = {}

    # Update existing data with new credentials data
    # This will overwrite fields that are present in new_creds_data
    # and keep fields that are only in existing_data.
    merged_data = {**existing_data, **new_creds_data}
    
    # Special handling for 'scopes' if it's a list, to potentially merge or replace
    # For 'scopes', typically the flow ensures the correct set. We'll just take the new one.
    if 'scopes' in new_creds_data:
        merged_data['scopes'] = new_creds_data['scopes']
    
    # Write the merged dictionary back to the file
    with open(TOKEN_FILE, "w") as token:
        json.dump(merged_data, token, indent=4) # Use indent for readability
    print("Credentials saved/updated in token.json.")


def get_credentials():
    """
    Loads credentials from token.json, or returns None if not found.
    Handles token refresh if the loaded token is expired.
    Ensures all datetime comparisons are consistently timezone-aware.
    """
    creds = None
    if os.path.exists(TOKEN_FILE):
        print(f"DEBUG: Loading credentials from {TOKEN_FILE}.")
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
            og_creds_expiry = creds.expiry  # Original expiry for debugging
            # --- START Critical Timezone Handling ---
            if creds.expiry and creds.expiry.tzinfo is None:
                creds.expiry = creds.expiry.replace(tzinfo=timezone.utc)
                print("DEBUG: Corrected naive creds.expiry to timezone-aware (UTC).")
            # --- END Critical Timezone Handling ---
            
            print(f"DEBUG: creds.expiry BEFORE comparison: {creds.expiry} (Type: {type(creds.expiry)}, Tzinfo: {creds.expiry.tzinfo})")

            current_utc_time = datetime.now(timezone.utc)
            is_expired = creds.expiry < current_utc_time if creds.expiry else True # Default to expired if expiry is None

            print(f"DEBUG: Current UTC time for comparison: {current_utc_time} (Type: {type(current_utc_time)}, Tzinfo: {current_utc_time.tzinfo})")
            print(f"DEBUG: Custom `is_expired` check result: {is_expired}")

            creds.expiry = og_creds_expiry
            # Check if token is expired and refresh if a refresh_token is available
            if is_expired and creds.refresh_token:
                print(f"DEBUG: Credentials from {TOKEN_FILE} expired, attempting refresh...")
                print(f"DEBUG: Refresh token present for refresh attempt: {creds.refresh_token is not None}")
                try:
                    creds.refresh(Request()) 
                    save_credentials(creds)
                    print(f"DEBUG: Credentials from {TOKEN_FILE} refreshed and updated. New expiry: {creds.expiry}. New access token length: {len(creds.token) if creds.token else 'N/A'}")
                    
                    # --- REPLACED creds.valid CHECK HERE ---
                    if not is_expired and creds.token: # Check if not expired AND access token exists
                        print("DEBUG: Credentials now valid after refresh (custom check).")
                        return creds
                    else:
                        print("WARNING: Credentials not valid after refresh attempt (custom check). This indicates an issue with the refreshed token itself or no access token.")
                        print(f"DEBUG: Refreshed token: {creds.token[:30]}...") 
                        print(f"DEBUG: Refreshed expiry: {creds.expiry}")
                        creds = None
                except Exception as e:
                    print(f"CRITICAL ERROR: Failed to refresh credentials from {TOKEN_FILE}: {type(e).__name__}: {e}")
                    creds = None
            elif creds.refresh_token:
                print("DEBUG: Credentials not expired, but refresh token is present.")
            else: # This branch means creds.expired is True, but no refresh_token
                print("DEBUG: Credentials expired, but no refresh token available for silent refresh.")

            # --- REPLACED FINAL creds.valid CHECK HERE ---
            if creds and not is_expired and creds.token: # Ensure it's not None, not expired, and has a token
                print("DEBUG: Credentials loaded and valid (after potential refresh, custom check).")
                return creds
            elif creds:
                print("DEBUG: Credentials loaded but not valid after refresh attempt (custom check).")
                return None
        except Exception as e:
            print(f"ERROR: Failed to load credentials from {TOKEN_FILE}: {type(e).__name__}: {e}. You may need to re-authorize.")
            return None
    
    print("DEBUG: No existing token.json or valid credentials found.")
    return None

def build_calendar_service(creds):
    """Builds and returns a Google Calendar API service object."""
    try:
        return build("calendar", "v3", credentials=creds)
    except Exception as e:
        print(f"Error building calendar service: {e}")
        return None


async def get_free_busy_slots(service, start_time: datetime, end_time: datetime, calendar_id: str = 'primary'):
    """
    Queries Google Calendar for free/busy information for a specific calendar.
    Returns a list of free 1-hour slots.
    """
    try:
        body = {
            "timeMin": start_time.isoformat(),
            "timeMax": end_time.isoformat(),
            "items": [{"id": calendar_id}]
        }
        result = service.freebusy().query(body=body).execute()
        busy_periods = result['calendars'][calendar_id]['busy']

        free_slots = []
        current_time = start_time
        while current_time < end_time:
            is_busy = False
            for period in busy_periods:
                busy_start = datetime.fromisoformat(period['start']).astimezone(timezone.utc)
                busy_end = datetime.fromisoformat(period['end']).astimezone(timezone.utc)
                if busy_start <= current_time < busy_end:
                    is_busy = True
                    break

            if not is_busy:
                free_slots.append({
                    'start': current_time,
                    'end': current_time + timedelta(hours=1)
                })

            current_time += timedelta(hours=1)
        # print(free_slots)
        return free_slots

    except HttpError as error:
        print(f"An error occurred during free/busy query: {error}")
        return []
    except Exception as e:
        print(f"An unexpected error occurred in get_free_busy_slots: {e}")
        return []


async def create_calendar_event(service, start_time: datetime, end_time: datetime,
                                summary: str, description: str, attendee_email: str,
                                calendar_id: str = 'primary'):
    """
    Creates a new event on the specified Google Calendar.
    Returns the created event resource.
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
            {'email': calendar_id}
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
        event = service.events().insert(
            calendarId=calendar_id,
            body=event,
            conferenceDataVersion=1
        ).execute()
        print(f"Event created: {event.get('htmlLink')}")
        return event
    except HttpError as error:
        print(f"An error occurred while creating event: {error}")
        raise
    except Exception as e:
        print(f"An unexpected error occurred in create_calendar_event: {e}")
        raise

