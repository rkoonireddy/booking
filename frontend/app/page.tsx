'use client'; // This directive is essential for a client component

import { useState, useMemo, useEffect } from 'react';
import { format, isSameDay } from 'date-fns';
import { toZonedTime, formatInTimeZone } from 'date-fns-tz';
import { toast } from 'sonner';
import { motion } from 'framer-motion'; // Import Framer Motion

import { getSlots, bookSlot, Slot, BookingRequest } from '@/lib/api';

// Shadcn UI Components
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
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
import { Skeleton } from '@/components/ui/skeleton';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import Image from 'next/image'; // Import Next.js Image component

const commonTimezones = [
  'America/New_York',
  'America/Chicago',
  'America/Denver',
  'America/Los_Angeles',
  'Europe/London',
  'Europe/Paris',
  'Europe/Berlin',
  'Europe/Zurich',
  'Asia/Tokyo',
  'Asia/Shanghai',
  'Asia/Kolkata',
  'Australia/Sydney',
  'UTC',
];

// Main client-side page component
export default function Home() {
  const [currentSlots, setCurrentSlots] = useState<Slot[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedDate, setSelectedDate] = useState<Date | undefined>(undefined);
  const [isBookingDialogOpen, setIsBookingDialogOpen] = useState(false);
  const [selectedSlot, setSelectedSlot] = useState<Slot | null>(null);
  const [bookedByName, setBookedByName] = useState('');
  const [bookedByEmail, setBookedByEmail] = useState('');
  const [description, setDescription] = useState('');
  const [isBookingLoading, setIsBookingLoading] = useState(false);
  const [userTimezone, setUserTimezone] = useState<string>('');

  useEffect(() => {
    const detectedTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    setUserTimezone(detectedTimezone);
    // console.log("Detected local timezone:", detectedTimezone);

    async function fetchInitialSlots() {
      try {
        setLoading(true);
        const fetchedSlots = await getSlots();
        // console.log("--- Initial Slots from Backend (getSlots response, UTC) ---");
        // console.log(fetchedSlots);
        // console.log("-----------------------------------------------------");
        setCurrentSlots(fetchedSlots);
        setError(null);
      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : 'An unknown error occurred while fetching slots.';
        // console.error("Failed to fetch slots:", err);
        setError(errorMessage);
        toast.error(`Failed to load slots: ${errorMessage}`);
      } finally {
        setLoading(false);
      }
    }
    fetchInitialSlots();
  }, []);

  const datesWithAvailableSlots = useMemo(() => {
    const dates = new Set<string>();
    if (!userTimezone) return [];

    currentSlots.forEach(slot => {
      if (!slot.is_booked) {
        const zonedDate = toZonedTime(new Date(slot.datetime_utc), userTimezone);
        dates.add(format(zonedDate, 'yyyy-MM-dd'));
      }
    });
    // console.log(`Dates with Available Slots (in ${userTimezone}):`, Array.from(dates));
    return Array.from(dates);
  }, [currentSlots, userTimezone]);

  const filteredSlots = useMemo(() => {
    if (!selectedDate || !userTimezone) {
      return [];
    }

    const filtered = currentSlots.filter(slot => {
      const zonedSlotDateTime = toZonedTime(new Date(slot.datetime_utc), userTimezone);
      return isSameDay(zonedSlotDateTime, selectedDate!) && !slot.is_booked;
    }).sort((a, b) => {
      const zonedTimeA = toZonedTime(new Date(a.datetime_utc), userTimezone).getTime();
      const zonedTimeB = toZonedTime(new Date(b.datetime_utc), userTimezone).getTime();
      return zonedTimeA - zonedTimeB;
    });

    // console.log(`Filtered Slots for ${selectedDate ? format(selectedDate, 'yyyy-MM-dd') : 'No Date'} (in ${userTimezone}):`, filtered);
    return filtered;
  }, [currentSlots, selectedDate, userTimezone]);

  const handleOpenBookingDialog = (slot: Slot) => {
    setSelectedSlot(slot);
    setBookedByName('');
    setBookedByEmail('');
    // Set a default or informative description
    setDescription('Brief description of the meeting purpose...');
    setIsBookingDialogOpen(true);
    // console.log("Selected Slot for Booking (UTC):", slot);
  };

  const handleBookSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedSlot) return;

    // Validate description is not empty if you want to make it mandatory
    if (!description.trim()) {
        toast.error('Please provide a description for your booking.');
        return;
    }

    setIsBookingLoading(true);
    try {
      const bookingDetails: BookingRequest = {
        booked_by_name: bookedByName,
        booked_by_email: bookedByEmail,
        description: description,
      };

      await bookSlot(selectedSlot.id, bookingDetails);

      // console.log("--- Before Optimistic Slot Update ---");
      // console.log("Prev currentSlots state:", currentSlots);
      // console.log("Slot being updated:", selectedSlot.id);

      setCurrentSlots(prevSlots => {
        const updatedSlots = prevSlots.map(s =>
          s.id === selectedSlot.id ? { ...s, is_booked: true } : s
        );
        // console.log("New currentSlots state after optimistic update:", updatedSlots);
        // console.log("---------------------------------------");
        return updatedSlots;
      });

      toast.success(`Slot booked successfully!`);
      setIsBookingDialogOpen(false);

    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'An unknown error occurred.';
      toast.error(`Booking failed: ${errorMessage}`);
      // console.error("Booking error:", err);
    } finally {
      setIsBookingLoading(false);
    }
  };

  // Framer Motion variants for fade-in animation
  const containerVariants = {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: {
        duration: 0.5,
        delay: 0.3,
        ease: "easeOut"
      }
    }
  };

  return (
    <motion.main
      // Changed background to a slightly off-white for better contrast with a potential new theme
      className="flex min-h-screen flex-col items-center justify-start p-8 md:p-12 bg-gray-100 text-gray-900"
      variants={containerVariants}
      initial="hidden"
      animate="visible"
    >
      <h1 className="text-4xl font-bold text-center mb-10 text-primary"> {/* Used text-primary for title */}
        Book a meeting with Rohit Koonireddy (RK)
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
                <Label htmlFor="timezone-select" className="mb-2 block text-sm font-medium text-foreground">Your Current Timezone</Label> {/* Use text-foreground */}
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
                disabled={(date) =>
                  !datesWithAvailableSlots.includes(format(date, 'yyyy-MM-dd'))
                }
                classNames={{
                  day_selected: "bg-primary text-primary-foreground hover:bg-primary hover:text-primary-foreground focus:bg-primary focus:text-primary-foreground",
                  day: "w-9 h-9",
                }}
              />
            </CardContent>
          </Card>

          <Card className="p-4 flex-1">
            <CardHeader className="p-0 pb-4 flex flex-row items-center justify-between">
              <div className="flex-1">
                <CardTitle className="text-lg">
                  {selectedDate && userTimezone
                    ? `Available Times on ${formatInTimeZone(selectedDate, userTimezone, 'MMM do, yyyy (EEEE)')}` // Changed date format for better readability
                    : 'Select a Date to See Times'}
                </CardTitle>
                <CardDescription>
                  {selectedDate && filteredSlots.length === 0 ? (
                    <p>No available slots for this date in <span className="font-semibold text-primary">{userTimezone}</span>.</p> // Highlight timezone
                  ) : (
                    !selectedDate && <p className="text-center text-muted-foreground">Please select a date from the calendar.</p> // Use muted-foreground
                  )}
                </CardDescription>
              </div>
              {/* User Photo Placeholder */}
              <div className="ml-4">
                <Image
                  src="/Rohit.jpg" // Assuming 'Rohit.jpg' is in your public directory
                  alt="User Profile"
                  width={60} // Slightly larger for better visibility
                  height={60}
                  className="rounded-full border-2 border-primary shadow-md" // Added border and shadow
                />
              </div>
            </CardHeader>
            <CardContent className="p-0">
              {filteredSlots.length > 0 ? (
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                  {filteredSlots.map((slot) => (
                    <motion.div
                      key={slot.id}
                      whileHover={{ scale: 1.05, backgroundColor: 'var(--primary)' }} // Smooth transition to primary on hover
                      transition={{ duration: 0.2 }}
                      className="w-full"
                    >
                      <Button
                        onClick={() => handleOpenBookingDialog(slot)}
                        disabled={slot.is_booked || isBookingLoading}
                        className="flex flex-col h-auto py-2 px-3 text-base bg-secondary text-secondary-foreground hover:bg-secondary/80 w-full" // Using secondary for time slots
                      >
                        <span className="font-semibold">
                          {formatInTimeZone(new Date(slot.datetime_utc), userTimezone, 'HH:mm')}
                        </span>
                        <span className="text-xs opacity-80 mt-1">
                          {formatInTimeZone(new Date(slot.datetime_utc), userTimezone, 'z')}
                        </span>
                      </Button>
                    </motion.div>
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
                  {formatInTimeZone(new Date(selectedSlot.datetime_utc), userTimezone, "EEEE, MMM do, yyyy 'at' HH:mm zzz")}
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
                  placeholder="e.g., Interview for Software Engineer role, Q&A about project X, etc." // Added placeholder
                  required // Made description required
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
    </motion.main>
  );
}