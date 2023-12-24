# pip install aiogram

import asyncio
import sqlite3
import os
import sys
import logging
from datetime import datetime

from models import Post, Interaction  # Импорт классов из models.py

from aiogram import Bot, Dispatcher
from aiogram import Router, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message, User

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from alembic.config import Config
from alembic import command

# Configure logging
logging.basicConfig(level=logging.INFO, stream=sys.stdout)

# Initialize Telegram Bot
bot_token = os.getenv("TELEGRAM_MEDIA_RATER_BOT_API")
if (bot_token is None):
    print('TELEGRAM_MEDIA_RATER_BOT_API is not set')
    sys.exit(1)

bot_name = "mediar0bot"
if (bot_name is None):
    print('TELEGRAM_MEDIA_RATER_BOT_NAME is not set')
    sys.exit(1)

router = Router()


# Constants
update_limit = 100
timeout = 120
db_path = "sqlite.db"
bot_id = 0


# Initialize SQLite
sqlite3.enable_callback_tracebacks(True)

# Initialize SQLite connection
db_connection = sqlite3.connect(db_path)

# Inline keyboard markup
new_post_ikm = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="👍", callback_data="+")
    , InlineKeyboardButton(text="👎", callback_data="-")]
])


# Functions
async def init_and_migrate_db():
    await migrate_database()


async def migrate_database():
    global db_connection
    logging.info('db migrate')
    db_connection.close()
    try:
        alembic_cfg = Config("alembic.ini")
        command.upgrade(alembic_cfg, "head")
        logging.info('db migrate done')
    except Exception as e:
        logging.error(f"Failed to migrate database: {e}")
    db_connection = sqlite3.connect(db_path)


@router.callback_query()
async def handle_callback_data(query: CallbackQuery):
    msg = query.message
    with db_connection:
        cursor = db_connection.cursor()
        if query.data in ["+", "-"]:
            logging.debug("Valid callback request")
            sql = f"SELECT * FROM Post WHERE ChatId = ? AND MessageId = ?;"
            cursor.execute(sql, (msg.chat.id, msg.message_id))
            data = cursor.fetchone()

            if data is None:
                print(
                    f"Cannot find post in the database, ChatId = {msg.chat.id}, MessageId = {msg.message_id}")
                return

            post = Post(*data)

            if post.posterId == query.from_user.id:
                await msg.bot.answer_callback_query(query.id, "Нельзя голосовать за свои посты!")
                return

            sql = f"SELECT * FROM Interaction WHERE ChatId = ? AND MessageId = ?;"
            cursor.execute(sql, (msg.chat.id, msg.message_id))
            data = cursor.fetchall()
            interactions = [Interaction(*row) for row in data]
            interaction = next(
                (i for i in interactions if i.userId == query.from_user.id), None)

            if interaction is not None:
                new_reaction = query.data == "+"
                if new_reaction == interaction.reaction:
                    print("No need to update reaction")
                    return
                sql = f"UPDATE Interaction SET Reaction = ? WHERE Id = ?;"
                cursor.execute(sql, (new_reaction, interaction.Id))
                interaction.reaction = new_reaction
            else:
                sql = f"INSERT INTO Interaction (ChatId, UserId, MessageId, Reaction, PosterId) VALUES (?, ?, ?, ?, ?);"
                cursor.execute(sql, (msg.chat.id, query.from_user.id,
                               msg.message_id, query.data == "+", post.posterId))
                interactions.append(Interaction(Reaction=query.data == "+"))

            likes = sum(1 for i in interactions if i.reaction)
            dislikes = len(interactions) - likes
            plus_text = f"{likes} 👍" if likes > 0 else "👍"
            minus_text = f"{dislikes} 👎" if dislikes > 0 else "👎"
            ikm = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton("+", callback_data="+", text=plus_text),
                 InlineKeyboardButton("-", callback_data="-", text=minus_text)]
            ])
            try:
                await msg.bot.edit_message_reply_markup(chat_id=msg.chat.id, message_id=msg.message_id, reply_markup=ikm)
            except Exception as ex:
                print(ex, "EditMessageReplyMarkupAsync")


@router.message(F.text == f"/text@{bot_name}" or F.text == "/text")
async def handle_media_message(msg: Message):
    try:
        if(msg.reply_to_message != None):
            if (not msg.reply_to_message.from_user.id == bot_id):
                await msg.answer("Эту команду нужно вызывать реплаем на текстовое сообщение или ссылку не от бота")
                return
            if (not msg.reply_to_message.text or msg.reply_to_message.text.isspace()):
                await msg.answer("Эту команду нужно вызывать реплаем на текстовое сообщение или ссылку")
                return
            await HandleTextReplyAsync(msg)
        else:
            await msg.answer("Эту команду нужно вызывать реплаем на текстовое сообщение или ссылку")
    except Exception as ex:
        print(ex, "Cannot handle media message")


async def HandleTextReplyAsync(msg: Message):
    reply_to = msg.reply_to_message
    from_user = reply_to.from_user
    new_message = await msg.bot.send_message(msg.chat.id, f"От @{from_user.username}:\n{reply_to.text}", reply_markup= new_post_ikm)
    try:
        await msg.bot.delete_message(msg.chat.id, msg.message_id)
    except Exception as ex:
        print(ex, "Cannot handle text reply")

    if (msg.from_user.id == from_user.id):
        await msg.bot.delete_message(chat_id=msg.chat.id, message_id=reply_to.message_id)
    
    sql = f"INSERT INTO Post (ChatId, PosterId, MessageId, timestamp) VALUES ( ?, ?, ?, ?);"
    cursor = db_connection.cursor()
    cursor.execute(sql, (msg.chat.id, from_user.id, new_message.message_id, datetime.utcnow().timestamp()))

@router.message(F.photo | F.video | F.document)
async def handle_media_message(msg: Message):
    logging.debug("Valid media message")
    from_user = msg.from_user
    try:
        who = GetFirstLast(from_user)

        caption = f"От [{who}](https://t.me/{from_user.username})"
        new_message = await msg.bot.copy_message(chat_id=msg.chat.id, from_chat_id=msg.chat.id, message_id=msg.message_id,
                                                 reply_markup=new_post_ikm, caption=caption, parse_mode="MarkdownV2")
        await msg.bot.delete_message(chat_id=msg.chat.id, message_id=msg.message_id)

        with db_connection:
            sql = f"INSERT INTO Post (ChatId, PosterId, MessageId, timestamp) VALUES ( ?, ?, ?, ?);"
            cursor = db_connection.cursor()
            cursor.execute(sql, (msg.chat.id, from_user.id,
                           new_message.message_id, datetime.utcnow().timestamp()))
    except Exception as ex:
        print(ex, "Cannot handle media message")


def GetFirstLast(from_user: User | None) -> str:
    first_name = from_user.first_name or ""
    last_name = from_user.last_name or ""
    who = f"{first_name} {last_name}".strip() or "анонима"
    return who
 

async def main() -> None:
    global bot_id
    await init_and_migrate_db()
    bot = Bot(token=bot_token)
    bot_id = (await bot.get_me()).id
    dp = Dispatcher()
    dp.include_routers(router)
    logging.info('bot started')
    await dp.start_polling(bot, skip_updates=True)


# Start the bot
if __name__ == '__main__':
    asyncio.run(main())
