# booking-backend/models.py

from typing import Optional
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import create_engine

# Import Base from your database.py
from database import Base, engine

class Slot(Base):
    __tablename__ = "slots" # Name of the database table

    id = Column(String, primary_key=True, index=True) # Using String for slot-X IDs
    datetime_utc = Column(DateTime, index=True) # Store UTC datetime
    is_booked = Column(Boolean, default=False)
    booked_by_name = Column(String, nullable=True) # Nullable because it's initially not booked
    booked_by_email = Column(String, nullable=True) # Nullable
    description = Column(String, nullable=True) # Nullable
    # Optional: Add a relationship if you expand with a separate 'Booking' table
    # For now, booking details are directly on the slot

# This function creates the database tables if they don't exist
def create_db_tables():
    Base.metadata.create_all(bind=engine)

# You might want to call this once when your application starts,
# or use Alembic for database migrations in a production setup.