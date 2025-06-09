// frontend/lib/api.ts

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL;

if (!BACKEND_URL) {
  throw new Error("NEXT_PUBLIC_BACKEND_URL is not defined in .env.local");
}

// Define the shape of a Slot as returned by your backend
export interface Slot {
  id: string;
  datetime_utc: string; // Use string for ISO format date/time
  is_booked: boolean;
}

// Define the shape of a BookingRequest for sending data to backend
export interface BookingRequest {
  booked_by_name: string;
  booked_by_email: string;
  description?: string; // Optional property
}

// Function to fetch available slots
export async function getSlots(): Promise<Slot[]> {
  const response = await fetch(`${BACKEND_URL}/slots`);
  if (!response.ok) {
    throw new Error(`Error fetching slots: ${response.statusText}`);
  }
  const data: Slot[] = await response.json();
  return data;
}

// Function to book a specific slot
export async function bookSlot(slotId: string, bookingDetails: BookingRequest): Promise<Slot> {
  const response = await fetch(`${BACKEND_URL}/slots/${slotId}/book`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(bookingDetails),
  });

  if (!response.ok) {
    const errorData = await response.json();
    throw new Error(`Error booking slot: ${response.statusText} - ${errorData.detail || 'Unknown error'}`);
  }
  const data: Slot = await response.json();
  return data;
}