# models.py
from datetime import datetime
from sqlalchemy import Column, Integer, BigInteger, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class Post(Base):
    __tablename__ = 'Post'
    Id = Column(Integer, primary_key=True)
    ChatId = Column(BigInteger, nullable=False)
    PosterId = Column(BigInteger, nullable=False)
    MessageId = Column(BigInteger, nullable=False)
    Timestamp = Column(DateTime, nullable=False, default=datetime.utcnow().timestamp())

    def __init__(self, id: int, chat_id: int, poster_id: int, message_id: int, timestamp: datetime):
        self.Id: int = id
        self.ChatId: int = chat_id
        self.PosterId: int = poster_id
        self.MessageId: int = message_id
        self.Timestamp: datetime = timestamp or datetime.utcnow().timestamp()


class Interaction(Base):
    __tablename__ = 'Interaction'
    Id = Column(Integer, primary_key=True)
    ChatId = Column(BigInteger, nullable=False)
    MessageId = Column(BigInteger, nullable=False)
    UserId = Column(BigInteger, nullable=False)
    Reaction = Column(Boolean, nullable=False)

    def __init__(self, id: int = 0, chat_id: int = 0, message_id: int = 0, user_id: int = 0, reaction: bool = True):
        self.Id: int = id
        self.ChatId: int = chat_id
        self.MessageId: int = message_id
        self.UserId: int = user_id
        self.Reaction: bool = reaction
