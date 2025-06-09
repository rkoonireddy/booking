# booking-backend/database.py

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

# SQLite database URL
# We'll store the database file in the same directory for simplicity
SQLALCHEMY_DATABASE_URL = "sqlite:///./sql_app.db" # This creates a file named sql_app.db

# For PostgreSQL (for production), it would look something like:
# SQLALCHEMY_DATABASE_URL = "postgresql://user:password@host:port/dbname"

# Create the SQLAlchemy engine
# connect_args is needed for SQLite to allow multiple threads to interact with the same connection
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

# Create a SessionLocal class for database sessions
# Each instance of SessionLocal will be a database session.
# It's not a connection, but a "holding zone" for objects that need to be persisted.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for our SQLAlchemy models
Base = declarative_base()

# Dependency to get a database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()