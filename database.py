import os

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Ensure the instance directory exists
if not os.path.exists("./instance"):
    os.makedirs("./instance")

# Update the database URL to save in the './instance' directory
SQLALCHEMY_DATABASE_URL = "sqlite:///./instance/poker_hands.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()
