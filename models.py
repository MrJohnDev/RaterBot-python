# models.py
from datetime import datetime
from sqlalchemy import Column, Integer, BigInteger, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class Post(Base):
    __tablename__ = 'post'
    id = Column(Integer, primary_key=True)
    chatId = Column(BigInteger, nullable=False)
    posterId = Column(BigInteger, nullable=False)
    messageId = Column(BigInteger, nullable=False)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow().timestamp())

    def __init__(self, id: int, chat_id: int, poster_id: int, message_id: int, timestamp: datetime):
        self.id: int = id
        self.chatId: int = chat_id
        self.posterId: int = poster_id
        self.messageId: int = message_id
        self.timestamp: datetime = timestamp or datetime.utcnow().timestamp()


class Interaction(Base):
    __tablename__ = 'interaction'
    id = Column(Integer, primary_key=True)
    chatId = Column(BigInteger, nullable=False)
    posterId = Column(BigInteger, nullable=False)
    messageId = Column(BigInteger, nullable=False)
    userId = Column(BigInteger, nullable=False)
    reaction = Column(Boolean, nullable=False)

    def __init__(self, id: int, chat_id: int, poster_id: int, message_id: int, user_id: int, reaction: bool):
        self.id: int = id
        self.chatId: int = chat_id
        self.posterId: int = poster_id
        self.messageId: int = message_id
        self.user_id: int = user_id
        self.reaction: bool = reaction
