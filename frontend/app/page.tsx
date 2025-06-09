'use client'; // This directive is essential for a client component

import { useState, useMemo, useEffect } from 'react';
import { format, isSameDay } from 'date-fns';
import { toast } from 'sonner';

import { getSlots, bookSlot, Slot, BookingRequest } from '@/lib/api';

// Shadcn UI Components
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
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
import { cn } from '@/lib/utils';
import { Skeleton } from '@/components/ui/skeleton';

// Main client-side page component
export default function Home() {
  const [currentSlots, setCurrentSlots] = useState<Slot[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedDate, setSelectedDate] = useState<Date | undefined>(undefined);

  const [isBookingDialogOpen, setIsBookingDialogOpen] = useState(false);
  const [selectedSlot, setSelectedSlot] = useState<Slot | null>(null);

  const [bookedByName, setBookedByName] = useState('');
  const [bookedByEmail, setBookedByEmail] = useState(''); // Corrected typo
  const [description, setDescription] = useState('');
  const [isBookingLoading, setIsBookingLoading] = useState(false);

  // --- Initial Data Fetch (Client-side) ---
  useEffect(() => {
    async function fetchInitialSlots() {
      try {
        setLoading(true);
        const fetchedSlots = await getSlots();
        // --- CONSOLE LOG HERE: Initial Slots Response ---
        console.log("--- Initial Slots from Backend (getSlots response) ---");
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
  }, []);

  // Calculate dates that have at least one available slot
  const datesWithAvailableSlots = useMemo(() => {
    const dates = new Set<string>();
    currentSlots.forEach(slot => {
      if (!slot.is_booked) {
        dates.add(format(new Date(slot.datetime_utc), 'yyyy-MM-dd'));
      }
    });
    // --- CONSOLE LOG HERE: Dates with Available Slots ---
    console.log("Dates with Available Slots:", Array.from(dates));
    return Array.from(dates);
  }, [currentSlots]);

  // Filter slots based on the selected date
  const filteredSlots = useMemo(() => {
    if (!selectedDate) {
      return [];
    }
    const filtered = currentSlots.filter(slot =>
      isSameDay(new Date(slot.datetime_utc), selectedDate!) && !slot.is_booked
    ).sort((a, b) => new Date(a.datetime_utc).getTime() - new Date(b.datetime_utc).getTime());
    // --- CONSOLE LOG HERE: Filtered Slots for Selected Date ---
    console.log(`Filtered Slots for ${selectedDate ? format(selectedDate, 'yyyy-MM-dd') : 'No Date'}:`, filtered);
    return filtered;
  }, [currentSlots, selectedDate]);

  const handleOpenBookingDialog = (slot: Slot) => {
    setSelectedSlot(slot);
    setBookedByName('');
    setBookedByEmail('');
    setDescription('');
    setIsBookingDialogOpen(true);
    // --- CONSOLE LOG HERE: Slot selected for booking ---
    console.log("Selected Slot for Booking:", slot);
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

      // The backend bookSlot endpoint will return the updated slot (potentially with is_booked: true)
      await bookSlot(selectedSlot.id, bookingDetails);

      // --- CONSOLE LOG HERE: Before Optimistic Update ---
      console.log("--- Before Optimistic Slot Update ---");
      console.log("Prev currentSlots state:", currentSlots);
      console.log("Slot being updated:", selectedSlot.id);

      // Optimistically update the UI: Mark the specific slot as booked in currentSlots state
      setCurrentSlots(prevSlots => {
        const updatedSlots = prevSlots.map(s =>
          s.id === selectedSlot.id ? { ...s, is_booked: true } : s
        );
        // --- CONSOLE LOG HERE: After Optimistic Update ---
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
        <div className="flex flex-col lg:flex-row gap-8 w-full max-w-6xl mb-10">
          <Card className="p-4 flex-1">
            <CardHeader className="p-0 pb-4">
              <CardTitle className="text-lg">Select a Date</CardTitle>
              <CardDescription>Click a date to see available times.</CardDescription>
            </CardHeader>
            <CardContent className="p-0">
              <Calendar
                mode="single"
                selected={selectedDate}
                onSelect={setSelectedDate}
                initialFocus
                className="rounded-md border mx-auto"
                disabled={(date) =>
                  !datesWithAvailableSlots.includes(format(date, 'yyyy-MM-dd'))
                }
                classNames={{
                  day_selected: "bg-primary text-primary-foreground hover:bg-primary hover:text-primary-foreground focus:bg-primary focus:text-primary-foreground",
                  day: (day) => {
                    const formattedDay = format(day, 'yyyy-MM-dd');
                    const hasAvailable = datesWithAvailableSlots.includes(formattedDay);
                    return cn(
                      hasAvailable && "font-semibold text-green-700 dark:text-green-300",
                      day.getDay() === 0 && "text-red-500",
                      day.getDay() === 6 && "text-blue-500",
                      selectedDate && isSameDay(day, selectedDate) && "bg-blue-500 text-white",
                      "w-9 h-9"
                    );
                  },
                }}
              />
            </CardContent>
          </Card>

          <Card className="p-4 flex-1">
            <CardHeader className="p-0 pb-4">
              <CardTitle className="text-lg">
                {selectedDate ? `Available Times on ${format(selectedDate, 'MMM do,PPPP')}` : 'Select a Date to See Times'}
              </CardTitle>
              <CardDescription>
                {selectedDate && filteredSlots.length === 0 && (
                  <p>No available slots for this date.</p>
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
                      <span className="font-semibold">{format(new Date(slot.datetime_utc), 'HH:mm')}</span>
                      <span className="text-xs opacity-80 mt-1">UTC</span>
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


      {selectedSlot && (
        <Dialog open={isBookingDialogOpen} onOpenChange={setIsBookingDialogOpen}>
          <DialogContent className="sm:max-w-[425px]">
            <DialogHeader>
              <DialogTitle>Book Slot {selectedSlot.id}</DialogTitle>
              <DialogDescription>
                Confirm your details to book the slot on{' '}
                {format(new Date(selectedSlot.datetime_utc), "EEEE, MMM do, yyyy 'at' HH:mm 'UTC'")}.
              </DialogDescription>
            </DialogHeader>
            <form onSubmit={handleBookSubmit} className="grid gap-4 py-4">
              <div className="grid grid-cols-4 items-center gap-4">
                <Label htmlFor="name" className="text-right">
                  Name
                </Label>
                <Input
                  id="name"
                  value={bookedByName}
                  onChange={(e) => setBookedByName(e.target.value)}
                  className="col-span-3"
                  required
                />
              </div>
              <div className="grid grid-cols-4 items-center gap-4">
                <Label htmlFor="email" className="text-right">
                  Email
                </Label>
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
                <Label htmlFor="description" className="text-right">
                  Description
                </Label>
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