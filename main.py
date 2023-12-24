# pip install aiogram

import asyncio
import sqlite3
import os
import sys
import logging
from datetime import datetime, timedelta

from aiogram.enums import ChatType
from aiogram.filters import and_f, or_f, invert_f

from models import Post, Interaction  # Импорт классов из models.py

from aiogram import Bot, Dispatcher
from aiogram import Router, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message, User, Chat

from alembic.config import Config
from alembic import command

import pandas as pd
from itertools import count

from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, stream=sys.stdout)

# Initialize Telegram Bot
bot_token = os.getenv("TELEGRAM_MEDIA_RATER_BOT_API")
if (bot_token is None):
    bot_token = os.environ['TELEGRAM_MEDIA_RATER_BOT_API']
    print('TELEGRAM_MEDIA_RATER_BOT_API is not set')
    # sys.exit(1)

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
    db_connection.execute("PRAGMA synchronous = OFF;")
    db_connection.execute("PRAGMA journal_mode = WAL;")
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
    # chatAndMessageIdParams = {'ChatId': msg.chat.id, 'MessageId': msg.message_id}
    chatAndMessageIdParams = (msg.chat.id, msg.message_id)
    updateData = query.data
    if (updateData not in ["+", "-"]):
        logging.warning(f"Invalid callback query data: {updateData}")
        return

    logging.info("Valid callback request")
    with db_connection:
        cursor = db_connection.cursor()
        sql = f"SELECT * FROM {Post.__tablename__} WHERE ChatId = ? AND MessageId = ?;"
        cursor.execute(sql, (msg.chat.id, msg.message_id))
        data = cursor.fetchone()

        if data is None:
            print(
                f"Cannot find post in the database, ChatId = {msg.chat.id}, MessageId = {msg.message_id}")
            try:
                await msg.bot.edit_message_reply_markup(msg.chat.id, msg.message_id, InlineKeyboardMarkup());
            except Exception as e:
                logging.warning(e, "Unable to set empty reply markup, trying to delete post")
                await msg.bot.delete_message(msg.chat.id, msg.message_id)
            sql = f"SELECT * FROM {Interaction.__tablename__} WHERE {Interaction.ChatId} = @ChatId AND {Interaction.MessageId} = @MessageId;"
            await db_connection.execute(sql, chatAndMessageIdParams)
            return
        
        post = Post(*data)

        if post.PosterId == query.from_user.id:
            await msg.bot.answer_callback_query(query.id, "Нельзя голосовать за свои посты!")
            return

        sql = f"SELECT * FROM {Interaction.__tablename__} WHERE ChatId = ? AND MessageId = ?;"
        cursor.execute(sql, chatAndMessageIdParams)
        data = cursor.fetchall()
        interactions = [Interaction(*row) for row in data]
        interaction = next(
            (i for i in interactions if i.UserId == query.from_user.id), None)

        new_reaction = updateData == "+"
        if interaction is not None:
            if new_reaction == interaction.Reaction:
                reaction =  "👍" if new_reaction else "👎"
                await msg.bot.answer_callback_query(query.id, f"Ты уже поставил {reaction} этому посту")
                print("No need to update reaction")
                return
            sql = f"UPDATE {Interaction.__tablename__} SET Reaction = ? WHERE Id = ?;"
            cursor.execute(sql, (new_reaction, interaction.Id))
            interaction.Reaction = new_reaction
        else:
            sql = f"INSERT INTO {Interaction.__tablename__} (ChatId, UserId, MessageId, Reaction, PosterId) VALUES (?, ?, ?, ?, ?);"
            cursor.execute(sql, (msg.chat.id, query.from_user.id,
                           msg.message_id, new_reaction, post.PosterId))
            interactions.append(Interaction(reaction=new_reaction))

        likes = sum(1 for i in interactions if i.Reaction)
        dislikes = len(interactions) - likes

        if (datetime.utcnow() - timedelta(minutes=5)).timestamp() > post.Timestamp and dislikes > 2 * likes + 3:
            logging.info(f"Deleting post. Dislikes = {dislikes}, Likes = {likes}")
            await msg.bot.delete_message(msg.chat.id, msg.message_id)

            sql = f"DELETE FROM {Post.__tablename__} WHERE {Post.Id} = @Id;"
            await db_connection.execute(sql, { post.Id })

            sql = f"DELETE FROM {Interaction.__tablename__} WHERE {Interaction.ChatId} = @ChatId AND {Interaction.MessageId} = @MessageId;"
            deletedRows = await db_connection.execute(sql, chatAndMessageIdParams)
            logging.debug(f"Deleted {deletedRows} rows from Interaction")
            
            await msg.bot.answer_callback_query(query.id, "Твой голос стал решающей каплей, этот пост удалён")
            return
            

        plus_text = f"{likes} 👍" if likes > 0 else "👍"
        minus_text = f"{dislikes} 👎" if dislikes > 0 else "👎"

        ikm = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=plus_text, callback_data="+"),
             InlineKeyboardButton(text=minus_text, callback_data="-")]
        ])
        try:
            await msg.bot.edit_message_reply_markup(msg.chat.id, msg.message_id, reply_markup=ikm)
        except Exception as ex:
            print(ex, "Edit Message Reply Markup")


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
    logging.info("New valid text message")
    reply_to = msg.reply_to_message
    from_user = reply_to.from_user
    new_message = await msg.bot.send_message(msg.chat.id, f"{AtMentionUsername(from_user)}:\n{reply_to.text}", reply_markup= new_post_ikm)
    try:
        await msg.bot.delete_message(msg.chat.id, msg.message_id)
    except Exception as ex: # TODO replace Exception
        logging.warning(ex, "Unable to delete message in HandleTextReplyAsync, duplicated update?")

    if (msg.from_user.id == from_user.id):
        await msg.bot.delete_message(chat_id=msg.chat.id, message_id=reply_to.message_id)

    await InsertIntoPosts(msg.chat.id, from_user.id, new_message.message_id)

@router.message(F.text == f"/top_posts_week@{bot_name}" or F.text == "/top_posts_week")
async def handle_top_week_posts(msg: Message):
    logging.info("New top posts week")
    await HandleTopWeekPosts(msg)

@router.message(F.text == f"/top_authors_month@{bot_name}" or F.text == "/top_authors_month")
async def handle_top_authors_month(msg: Message):
    logging.info("New top authors month")
    await HandleTopMonthAuthors(msg)

async def HandleTopWeekPosts(msg: Message):
    chat = msg.chat
    if (chat.type != ChatType.SUPERGROUP and (not chat.username or chat.username.isspace())):
        await msg.bot.send_message(chat, "Этот чат не является супергруппой и не имеет имени: нет возможности оставлять ссылки на посты")
        logging.info(f"{(HandleTopWeekPosts)} - unable to link top posts, skipping")
        return
    
    week_ago = (datetime.utcnow() - timedelta(days=7)).timestamp()

    sql_params = {'TimeAgo': week_ago, 'ChatId': chat.id}
    sql  = GetMessageIdPlusCountPosterIdSql()
    plus_query = pd.read_sql_query(sql, db_connection, params=sql_params)


    plus = dict(zip(plus_query['MessageId'], plus_query['COUNT(*)']))
    messageIdToUserId = dict(zip(plus_query['MessageId'], plus_query['PosterId']))

    # Если нет плюсов, отправляем сообщение и завершаем выполнение
    if not plus:
        await msg.bot.send_message(chat.id, "Не найдено заплюсованных постов за последнюю неделю")
        logging.info(f"handle_top_week_posts - no upvoted posts, skipping")
        return
    
    # Запрос для получения минусов
    sql = GetMessageIdMinusCountSql()
    
    minus_query = pd.read_sql_query(sql, db_connection, params=sql_params)
    
    minus = dict(zip(minus_query['MessageId'], minus_query['COUNT(*)']))

    userIdToUser = {}

    # Вычитаем минусы из плюсов
    keys = list(plus.keys())
    for key in keys:
        plus[key] -= minus.get(key, 0)

    # Сортируем по убыванию и берем топ-10
    top_posts = sorted(plus.items(), key=lambda x: x[1], reverse=True)[:20]


    userIdToUser = {}

    for messageId, userId in messageIdToUserId.items():
        member = await msg.bot.get_chat_member(chat.id, userId)
        userIdToUser[userId] = member.user


    # Формируем сообщение с топ-10
    message = "Топ постов за последнюю неделю:\n"
    i = 0
    sg = chat.type == ChatType.SUPERGROUP
    for item in top_posts:
        plus_symb = '\+'

        userId = messageIdToUserId[item[0]]
        user = userIdToUser[userId]
        
        link = link_to_supergroup_message(chat.id, item[0]) if sg else link_to_group_with_name_message(chat, item[0])
        message += f"{GetPlace(i)} [От {UserEscaped(user)}]({link}) "
        message += f"{plus_symb if item[1] > 0 else ''}{item[1]}\n"
        i += 1

    # Отправляем сообщение
    await msg.bot.send_message(chat.id, message, parse_mode="MarkdownV2")


async def HandleTopMonthAuthors(msg: Message):
    chat = msg.chat
    if (chat.type != ChatType.SUPERGROUP and (not chat.username or chat.username.isspace())):
        await msg.bot.send_message(chat, "Этот чат не является супергруппой и не имеет имени: нет возможности оставлять ссылки на посты")
        logging.info(f"{(HandleTopMonthAuthors)} - unable to link top autors, skipping")
        return
    
    month_ago = (datetime.utcnow() - timedelta(days=30)).timestamp()


    sql_params = {'TimeAgo': month_ago, 'ChatId': chat.id}
    sql  = GetMessageIdPlusCountPosterIdSql()
    plus_query = pd.read_sql_query(sql, db_connection, params=sql_params)

    plus = dict(zip(plus_query['MessageId'], plus_query['COUNT(*)']))
    messageIdToUserId = dict(zip(plus_query['MessageId'], plus_query['PosterId']))
    
    # Если нет плюсов, отправляем сообщение и завершаем выполнение
    if not plus:
        await msg.bot.send_message(chat.id, "Не найдено заплюсованных постов за последний месяц")
        logging.info(f"handle_top_month_authors - no upvoted posts, skipping")
        return
    
    # Группировка данных и подсчет H-индекса
    grouped_data = {}
    for poster_id, group in plus_query.groupby('PosterId'):
        h_index = sum(plus_count >= i + 1 for i, plus_count in enumerate(sorted(group['COUNT(*)'], reverse=True)))
        likes = sum(group['COUNT(*)'])
        grouped_data[poster_id] = {'Key': poster_id, 'Hindex': h_index, 'Likes': likes}

    # Сортировка и взятие топ-10
    top_authors = sorted(grouped_data.values(), key=lambda x: (x['Hindex'], x['Likes']), reverse=True)[:10]

    userIdToUser = {}


    for messageId, userId in messageIdToUserId.items():
        member = await msg.bot.get_chat_member(chat.id, userId)
        userIdToUser[userId] = member.user
    

    message = "Топ авторов за последний месяц:\n"
    i = 0
    for item in top_authors:
        user = userIdToUser[item['Key']]
        message += f"{GetPlace(i)} {GetFirstLastName(user)} очков: {item['Hindex']}, апвоутов: {item['Likes']}"
        i += 1

    # Отправляем сообщение
    await msg.bot.send_message(chat.id, message, parse_mode="MarkdownV2")
  

@router.message(F.caption.contains('/skip') | F.caption.contains('#skip') | F.caption.contains('/ignore') | F.caption.contains('#ignore'))
async def handle_media_message(msg: Message):
    logging.info("Media message that should be ignored")

# @router.message(and_f((F.photo | F.video | F.document), invert_f(F.caption.contains('/skip') | F.caption.contains('#skip') | F.caption.contains('/ignore') | F.caption.contains('#ignore'))))
@router.message(F.photo | F.video | F.document)
async def handle_media_message(msg: Message):
    logging.info("New valid media message")
    from_user = msg.from_user
    try:
        new_message = await msg.bot.copy_message(chat_id=msg.chat.id, from_chat_id=msg.chat.id, message_id=msg.message_id,
                                                 reply_markup=new_post_ikm, caption=MentionUsername(from_user), parse_mode="MarkdownV2")
        await msg.bot.delete_message(chat_id=msg.chat.id, message_id=msg.message_id)
        await InsertIntoPosts(msg.chat.id, from_user.id,new_message.message_id)
    except Exception as ex:
        print(ex, "Cannot handle media message")


async def InsertIntoPosts(chat_id: int, poster_id: int, message_id: int):
    try:
        with db_connection:
            sql = f"INSERT INTO {Post.__tablename__} (ChatId, PosterId, MessageId, Timestamp) VALUES ( ?, ?, ?, ?);"
            cursor = db_connection.cursor()
            cursor.execute(sql, (chat_id, poster_id, message_id, datetime.utcnow().timestamp()))
    except Exception as ex:
        print(ex, "Cannot Insert Into Post")


def GetMessageIdPlusCountPosterIdSql() -> str:
    sql_plus = (
        f"SELECT {Interaction.MessageId}, COUNT(*), {Interaction.PosterId}"
        f" FROM {Post.__tablename__} INNER JOIN {Interaction.__tablename__} ON {Post.MessageId} = {Interaction.MessageId}"
        f" WHERE {Post.ChatId} = @ChatId AND {Interaction.ChatId} = @ChatId AND {Post.Timestamp} > @TimeAgo AND {Interaction.Reaction} = true"
        f" GROUP BY {Interaction.MessageId};"
    )
    return sql_plus


def GetMessageIdMinusCountSql() -> str:
    sql_minus = (
        f"SELECT {Interaction.MessageId}, COUNT(*)"
        f" FROM {Post.__tablename__} INNER JOIN {Interaction.__tablename__} ON {Post.MessageId} = {Interaction.MessageId}"
        f" WHERE {Post.ChatId} = @ChatId AND {Interaction.ChatId} = @ChatId AND {Post.Timestamp} > @TimeAgo AND {Interaction.Reaction} = false"
        f" GROUP BY {Interaction.MessageId};"
    )
    return sql_minus

def link_to_supergroup_message(chat_id: int, message_id: int):
    return f"https://t.me/c/{str(chat_id)[4:]}/{message_id}"

def link_to_group_with_name_message(chat: Chat, message_id: int):
    return f"https://t.me/{chat.username}/{message_id}"

def MentionUsername(from_user: User | None) -> str:
    whoEscaped = UserEscaped(from_user)
    return f"От [{whoEscaped}](tg://user?id={from_user.id})"

def UserEscaped(from_user: User | None) -> str:
    _should_be_escaped = set('_*[]()~`>#+-=|{}.!')

    who = GetFirstLastName(from_user)
    who_escaped = ''

    for c in who:
        if c in _should_be_escaped:
            who_escaped += '\\'
        who_escaped += c

    return  str(who_escaped)

def AtMentionUsername(from_user: User | None) -> str:
    if(not from_user.username or from_user.username.isspace()):
        who = GetFirstLastName(from_user)
        return f"поехавшего {who} без ника в телеге"
    return f"От @{from_user.username}"

def GetFirstLastName(from_user: User | None) -> str:
    first_name = from_user.first_name or ""
    last_name = from_user.last_name or ""
    who = f"{first_name} {last_name}".strip()

    if(not who or who.isspace()):
        who = "анонима"
    return who
 
def GetPlace(i: int) -> str:
    return {0: '🥇', 1: '🥈', 2: '🥉'}.get(i, f"{i + 1}")

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
