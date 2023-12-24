# models.py
from datetime import datetime


class Post:
    def __init__(self, id: int, chat_id: int, poster_id: int, message_id: int, timestamp: datetime):
        self.id: int = id
        self.chat_id: int = chat_id
        self.poster_id: int = poster_id
        self.message_id: int = message_id
        self.timestamp: datetime = timestamp or datetime.now()


class Interaction:
    def __init__(self, id: int, chat_id: int, poster_id: int, message_id: int, user_id: int, reaction: bool):
        self.id: int = id
        self.chat_id: int = chat_id
        self.poster_id: int = poster_id
        self.message_id: int = message_id
        self.user_id: int = user_id
        self.reaction: bool = reaction
