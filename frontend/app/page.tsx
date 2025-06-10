'use client'; // This directive is essential for a client component

import { useState, useMemo, useEffect } from 'react';
import { format, isSameDay } from 'date-fns'; // Keep format for general date handling if needed, but use date-fns-tz for zoned formatting
import { toZonedTime, formatInTimeZone } from 'date-fns-tz'; // Correct imports for timezone handling
import { toast } from 'sonner';

import { getSlots, bookSlot, Slot, BookingRequest } from '@/lib/api';

// Shadcn UI Components
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'; //CardFooter,
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Toaster } from 'sonner';
import { Calendar } from '@/components/ui/calendar';
// import { cn } from '@/lib/utils';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'; // Import Select components

// A more comprehensive list of common timezones, or you could fetch this dynamically
// For simplicity, we'll use a hardcoded list for now.
// In a real application, you might use a library like `tz-lookup` or a curated list.
const commonTimezones = [
  'America/New_York',
  'America/Chicago',
  'America/Denver',
  'America/Los_Angeles',
  'Europe/London',
  'Europe/Paris',
  'Europe/Berlin',
  'Europe/Zurich', // Added for Switzerland context
  'Asia/Tokyo',
  'Asia/Shanghai',
  'Asia/Kolkata',
  'Australia/Sydney',
  'UTC', // Keep UTC as an option
];

// Main client-side page component
export default function Home() {
  const [currentSlots, setCurrentSlots] = useState<Slot[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // selectedDate will represent a date in the *selected timezone* for calendar display/filtering
  const [selectedDate, setSelectedDate] = useState<Date | undefined>(undefined);

  const [isBookingDialogOpen, setIsBookingDialogOpen] = useState(false);
  const [selectedSlot, setSelectedSlot] = useState<Slot | null>(null);

  const [bookedByName, setBookedByName] = useState('');
  const [bookedByEmail, setBookedByEmail] = useState('');
  const [description, setDescription] = useState('');
  const [isBookingLoading, setIsBookingLoading] = useState(false);

  // State to hold the currently selected timezone by the user
  const [userTimezone, setUserTimezone] = useState<string>('');

  // --- Initial Data Fetch and Timezone Detection (Client-side) ---
  useEffect(() => {
    // 1. Detect user's local system timezone and set it as default
    const detectedTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    // Check if the detected timezone is in our common list, otherwise default to a reasonable one or add it.
    // For now, we'll just set it. If it's not in the dropdown, the user won't be able to select it again from the list.
    setUserTimezone(detectedTimezone);
    console.log("Detected local timezone:", detectedTimezone);

    // 2. Fetch initial slots from the backend (they are always in UTC)
    async function fetchInitialSlots() {
      try {
        setLoading(true);
        const fetchedSlots = await getSlots();
        console.log("--- Initial Slots from Backend (getSlots response, UTC) ---");
        console.log(fetchedSlots);
        console.log("-----------------------------------------------------");
        setCurrentSlots(fetchedSlots);
        setError(null);
      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : 'An unknown error occurred while fetching slots.';
        console.error("Failed to fetch slots:", err);
        setError(errorMessage);
        toast.error(`Failed to load slots: ${errorMessage}`);
      } finally {
        setLoading(false);
      }
    }
    fetchInitialSlots();
  }, []); // Empty dependency array means this runs once on mount

  // Calculate dates that have at least one available slot, converting UTC to the selected userTimezone
  const datesWithAvailableSlots = useMemo(() => {
    const dates = new Set<string>();
    if (!userTimezone) return []; // Don't calculate until timezone is set

    currentSlots.forEach(slot => {
      if (!slot.is_booked) {
        // Convert the UTC slot datetime to the selected userTimezone's local time
        const zonedDate = toZonedTime(new Date(slot.datetime_utc), userTimezone);
        // Format to 'yyyy-MM-dd' to get the date part in the selected timezone
        dates.add(format(zonedDate, 'yyyy-MM-dd'));
      }
    });
    console.log(`Dates with Available Slots (in ${userTimezone}):`, Array.from(dates));
    return Array.from(dates);
  }, [currentSlots, userTimezone]); // Recalculate if slots or timezone change

  // Filter slots based on the selected date (which implicitly represents a date in the current userTimezone)
  // and convert the slot times to the selected userTimezone for display and sorting
  const filteredSlots = useMemo(() => {
    if (!selectedDate || !userTimezone) {
      return [];
    }

    const filtered = currentSlots.filter(slot => {
      // Convert the UTC slot datetime to the selected userTimezone's local time
      const zonedSlotDateTime = toZonedTime(new Date(slot.datetime_utc), userTimezone);
      // Compare only the date part with the selectedDate (which is already considered in the user's timezone context)
      return isSameDay(zonedSlotDateTime, selectedDate!) && !slot.is_booked;
    }).sort((a, b) => {
      // Sort by the time in the selected userTimezone
      const zonedTimeA = toZonedTime(new Date(a.datetime_utc), userTimezone).getTime();
      const zonedTimeB = toZonedTime(new Date(b.datetime_utc), userTimezone).getTime();
      return zonedTimeA - zonedTimeB;
    });

    console.log(`Filtered Slots for ${selectedDate ? format(selectedDate, 'yyyy-MM-dd') : 'No Date'} (in ${userTimezone}):`, filtered);
    return filtered;
  }, [currentSlots, selectedDate, userTimezone]); // Recalculate if slots, selected date, or timezone change

  const handleOpenBookingDialog = (slot: Slot) => {
    setSelectedSlot(slot);
    setBookedByName('');
    setBookedByEmail('');
    setDescription('');
    setIsBookingDialogOpen(true);
    console.log("Selected Slot for Booking (UTC):", slot);
  };

  // Function to handle booking submission
  const handleBookSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedSlot) return;

    setIsBookingLoading(true);
    try {
      const bookingDetails: BookingRequest = {
        booked_by_name: bookedByName,
        booked_by_email: bookedByEmail,
        description: description,
      };

      // We send the original slot ID (which refers to the UTC slot) to the backend.
      // The backend doesn't need to know the user's display timezone for booking.
      await bookSlot(selectedSlot.id, bookingDetails);

      console.log("--- Before Optimistic Slot Update ---");
      console.log("Prev currentSlots state:", currentSlots);
      console.log("Slot being updated:", selectedSlot.id);

      // Optimistically update the UI: Mark the specific slot as booked in currentSlots state
      setCurrentSlots(prevSlots => {
        const updatedSlots = prevSlots.map(s =>
          s.id === selectedSlot.id ? { ...s, is_booked: true } : s
        );
        console.log("New currentSlots state after optimistic update:", updatedSlots);
        console.log("---------------------------------------");
        return updatedSlots;
      });

      toast.success(`Slot booked successfully!`);
      setIsBookingDialogOpen(false);

    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'An unknown error occurred.';
      toast.error(`Booking failed: ${errorMessage}`);
      console.error("Booking error:", err);
    } finally {
      setIsBookingLoading(false);
    }
  };

  return (
    <main className="flex min-h-screen flex-col items-center justify-start p-8 md:p-12 bg-gray-50">
      <h1 className="text-4xl font-bold text-center mb-10 text-gray-800">
        Book an Interview Slot
      </h1>

      {error && (
        <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded relative mb-6 w-full max-w-xl" role="alert">
          <strong className="font-bold">Error:</strong>
          <span className="block sm:inline ml-2">{error}</span>
          <p className="mt-2 text-sm">Please ensure your backend is running and accessible at `{process.env.NEXT_PUBLIC_BACKEND_URL}`.</p>
        </div>
      )}

      {loading && !error ? (
        // Skeleton Loaders
        <div className="flex flex-col lg:flex-row gap-8 w-full max-w-6xl mb-10">
          <Card className="p-4 flex-1">
            <CardHeader className="p-0 pb-4">
              <Skeleton className="h-6 w-48 mb-2" />
              <Skeleton className="h-4 w-64" />
            </CardHeader>
            <CardContent className="p-0">
              <Skeleton className="h-[300px] w-full rounded-md" />
            </CardContent>
          </Card>
          <Card className="p-4 flex-1">
            <CardHeader className="p-0 pb-4">
              <Skeleton className="h-6 w-56 mb-2" />
              <Skeleton className="h-4 w-40" />
            </CardHeader>
            <CardContent className="p-0">
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                {[...Array(6)].map((_, i) => (
                  <Skeleton key={i} className="h-14 w-full" />
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      ) : (
        // Main Content
        <div className="flex flex-col lg:flex-row gap-8 w-full max-w-6xl mb-10">
          <Card className="p-4 flex-1">
            <CardHeader className="p-0 pb-4">
              <CardTitle className="text-lg">Select a Date</CardTitle>
              <CardDescription>Click a date to see available times.</CardDescription>
              {/* Timezone Selection Dropdown */}
              <div className="mt-4">
                <Label htmlFor="timezone-select" className="mb-2 block text-sm font-medium text-gray-700">Your Current Timezone</Label>
                <Select value={userTimezone} onValueChange={setUserTimezone}>
                  <SelectTrigger id="timezone-select" className="w-full">
                    <SelectValue placeholder="Select your timezone" />
                  </SelectTrigger>
                  <SelectContent>
                    {commonTimezones.map((tz) => (
                      <SelectItem key={tz} value={tz}>
                        {tz}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </CardHeader>
            <CardContent className="p-0">
              {/* Calendar Component */}
              <Calendar
                mode="single"
                selected={selectedDate}
                onSelect={setSelectedDate}
                initialFocus
                className="rounded-md border mx-auto"
                // Disable dates that have no available slots in the selected timezone
                disabled={(date) =>
                  !datesWithAvailableSlots.includes(format(date, 'yyyy-MM-dd'))
                }
                classNames={{
                  day_selected: "bg-primary text-primary-foreground hover:bg-primary hover:text-primary-foreground focus:bg-primary focus:text-primary-foreground",
                  day: "w-9 h-9",
                }}
                // Removed dayClassName prop as it's not supported by Calendar/DayPicker
              />
            </CardContent>
          </Card>

          <Card className="p-4 flex-1">
            <CardHeader className="p-0 pb-4">
              <CardTitle className="text-lg">
                {selectedDate && userTimezone
                  // Display the selected date formatted in the chosen timezone
                  ? `Available Times on ${formatInTimeZone(selectedDate, userTimezone, 'MMM do, yyyy')}`
                  : 'Select a Date to See Times'}
              </CardTitle>
              <CardDescription>
                {selectedDate && filteredSlots.length === 0 && (
                  <p>No available slots for this date in {userTimezone}.</p>
                )}
              </CardDescription>
            </CardHeader>
            <CardContent className="p-0">
              {filteredSlots.length > 0 ? (
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                  {filteredSlots.map((slot) => (
                    <Button
                      key={slot.id}
                      onClick={() => handleOpenBookingDialog(slot)}
                      disabled={slot.is_booked || isBookingLoading}
                      className="flex flex-col h-auto py-2 px-3 text-base"
                    >
                      {/* Display the slot time converted to the selected timezone */}
                      <span className="font-semibold">
                        {formatInTimeZone(new Date(slot.datetime_utc), userTimezone, 'HH:mm')}
                      </span>
                      {/* Display a simplified timezone abbreviation */}
                      <span className="text-xs opacity-80 mt-1">
                        {formatInTimeZone(new Date(slot.datetime_utc), userTimezone, 'z')}
                      </span>
                    </Button>
                  ))}
                </div>
              ) : (
                selectedDate && !error && <p className="text-center text-gray-600">No available times found for this date.</p>
              )}
              {!selectedDate && !error && <p className="text-center text-gray-600">Please select a date from the calendar.</p>}
            </CardContent>
          </Card>
        </div>
      )}

      {/* Booking Confirmation Dialog */}
      {selectedSlot && (
        <Dialog open={isBookingDialogOpen} onOpenChange={setIsBookingDialogOpen}>
          <DialogContent className="sm:max-w-[425px]">
            <DialogHeader>
              <DialogTitle>Book Slot</DialogTitle>
              <DialogDescription>
                Confirm your details to book the slot on{' '}
                {/* Display the selected slot time in the user's chosen timezone */}
                {formatInTimeZone(new Date(selectedSlot.datetime_utc), userTimezone, "EEEE, MMM do, yyyy 'at' HH:mm zzz")}.
              </DialogDescription>
            </DialogHeader>
            <form onSubmit={handleBookSubmit} className="grid gap-4 py-4">
              <div className="grid grid-cols-4 items-center gap-4">
                <Label htmlFor="name" className="text-right">Name</Label>
                <Input
                  id="name"
                  value={bookedByName}
                  onChange={(e) => setBookedByName(e.target.value)}
                  className="col-span-3"
                  required
                />
              </div>
              <div className="grid grid-cols-4 items-center gap-4">
                <Label htmlFor="email" className="text-right">Email</Label>
                <Input
                  id="email"
                  type="email"
                  value={bookedByEmail}
                  onChange={(e) => setBookedByEmail(e.target.value)}
                  className="col-span-3"
                  required
                />
              </div>
              <div className="grid grid-cols-4 items-center gap-4">
                <Label htmlFor="description" className="text-right">Description</Label>
                <Textarea
                  id="description"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  className="col-span-3"
                  rows={3}
                />
              </div>
              <DialogFooter>
                <Button type="submit" disabled={isBookingLoading}>
                  {isBookingLoading ? 'Booking...' : 'Confirm Booking'}
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      )}
      <Toaster />
    </main>
  );
}