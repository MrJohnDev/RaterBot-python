# models.py
from datetime import datetime
from sqlalchemy import Column, Integer, BigInteger, DateTime, Boolean, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()

class Post(Base):
    __tablename__ = 'post'
    id = Column(Integer, primary_key=True)
    chat_id = Column(BigInteger, nullable=False)
    poster_id = Column(BigInteger, nullable=False)
    message_id = Column(BigInteger, nullable=False)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)

class Interaction(Base):
    __tablename__ = 'interaction'
    id = Column(Integer, primary_key=True)
    chat_id = Column(BigInteger, nullable=False)
    poster_id = Column(BigInteger, nullable=False)
    message_id = Column(BigInteger, nullable=False)
    user_id = Column(BigInteger, nullable=False)
    reaction = Column(Boolean, nullable=False)

# Create SQLite database engine
engine = create_engine('sqlite:///sqlite.db')

# Create tables in the database
Base.metadata.create_all(engine)

# Create a session factory
SessionFactory = sessionmaker(bind=engine)
