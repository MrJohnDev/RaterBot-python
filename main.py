# pip install aiogram
from enum import Enum
import asyncio
import configparser
import sqlite3
import os, re
import sys
import logging
from datetime import datetime, timedelta

from aiogram.enums import ChatType
from aiogram.filters import and_f, or_f, invert_f, Command

from models import Post, Interaction  # Импорт классов из models.py

from aiogram import Bot, Dispatcher
from aiogram import Router, F
from aiogram import types

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message, User, Chat

from aiogram.enums import ChatAction
from aiogram.enums import ParseMode

from alembic.config import Config
from alembic import command

import pandas as pd

from dotenv import load_dotenv

from yt import run_yt_dlp

from tg.types import Album
from tg.middlewares.album import AlbumMiddleware

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, stream=sys.stdout)

previous_media_group_id = ""

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
timeout = 1800
db_dir = 'db'
db_name = 'sqlite.db'
db_path = os.path.join(db_dir, db_name)
bot_id = 0

def update_db_path(file_path: str):
    if not os.path.exists(db_dir):
        try:
            os.makedirs(db_dir)
        except Exception as e:
            logging.exception(f"Exception during directory creation: {e}")
    # Read the alembic.ini file
    config = configparser.ConfigParser()
    config.read('alembic.ini')

    # Set the dynamic URL in the [alembic] section
    config.set('alembic', 'sqlalchemy.url', "sqlite:///" + file_path.replace('\\', ''))

    # Write the modified configuration back to alembic.ini
    with open('alembic.ini', 'w') as config_file:
        config.write(config_file)


# Initialize SQLite
sqlite3.enable_callback_tracebacks(True)



# Inline keyboard markup
new_post_ikm = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="👍", callback_data="+")
    , InlineKeyboardButton(text="👎", callback_data="-")]
])


class Period(Enum):
    Day = timedelta(days=1)
    Week = timedelta(days=7)
    Month = timedelta(days=30)


def ForLast(period: Period) -> str:
    match period:
        case Period.Day:
            return "последний день"
        case Period.Week:
            return "последнюю неделю"
        case Period.Month:
            return "последний месяц"
        case _:
            return "последние"


async def init_and_migrate_db():
    update_db_path(db_path)
    await migrate_database()
    db_connection.execute("PRAGMA synchronous = NORMAL;")
    db_connection.execute("PRAGMA vacuum;")
    db_connection.execute("PRAGMA temp_store = memory;")


async def migrate_database():
    global db_connection
    logging.info('db migrate')
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
                await msg.bot.edit_message_reply_markup(msg.chat.id, msg.message_id, InlineKeyboardMarkup())
            except Exception as e:
                logging.warning(
                    e, "Unable to set empty reply markup, trying to delete post")
                await msg.bot.delete_message(msg.chat.id, msg.message_id)
            sql = f"SELECT * FROM {Post.__tablename__} WHERE {Post.ChatId} = @ChatId AND {Post.MessageId} = @MessageId;"
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
                reaction = "👍" if new_reaction else "👎"
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
            logging.info(
                f"Deleting post. Dislikes = {dislikes}, Likes = {likes}")
            await msg.bot.delete_message(msg.chat.id, msg.message_id)

            sql = f"DELETE FROM {Post.__tablename__} WHERE {Post.Id} = @Id;"
            await db_connection.execute(sql, {post.Id})

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

    if (msg.message_id % 50 == 0):
        logging.info('DB optimize')
        await db_connection.execute("PRAGMA optimize;")


@router.message(Command("text"))
async def handle_text_message(msg: Message):
    try:
        if (msg.reply_to_message == None):
            m = await msg.reply("Эту команду нужно вызывать реплаем на текстовое сообщение или ссылку")

            asyncio.create_task(remove_after_some_time(
                msg.bot, msg.chat, m.message_id))
            asyncio.create_task(remove_after_some_time(
                msg.bot, msg.chat, msg.message_id))
            return

        if (msg.reply_to_message.from_user.id != bot_id):
            m = await msg.reply("Эту команду нужно вызывать реплаем на текстовое сообщение или ссылку не от бота")
            asyncio.create_task(remove_after_some_time(
                msg.bot, msg.chat, m.message_id))
            asyncio.create_task(remove_after_some_time(
                msg.bot, msg.chat, msg.message_id))
            return

        if (not msg.reply_to_message.text or msg.reply_to_message.text.isspace()):
            m = await msg.reply("Эту команду нужно вызывать реплаем на текстовое сообщение или ссылку")

            asyncio.create_task(remove_after_some_time(
                msg.bot, msg.chat, m.message_id))
            asyncio.create_task(remove_after_some_time(
                msg.bot, msg.chat, msg.message_id))
            return
        await HandleTextReplyAsync(msg)
    except Exception as ex:
        print(ex, "Cannot handle media message")


@router.message(Command("delete"))
async def handle_delete_message(msg: Message):
    try:
        if (msg.reply_to_message == None):
            m = await msg.reply("Эту команду нужно вызывать реплаем на текстовое сообщение или ссылку")

            asyncio.create_task(remove_after_some_time(
                msg.bot, msg.chat, m.message_id))
            asyncio.create_task(remove_after_some_time(
                msg.bot, msg.chat, msg.message_id))
            return

        if msg.reply_to_message.from_user is None:
            return

        if (msg.reply_to_message.from_user.id != bot_id):
            m = await msg.reply("Эту команду нужно вызывать реплаем на текстовое сообщение или ссылку не от бота")
            asyncio.create_task(remove_after_some_time(
                msg.bot, msg.chat, m.message_id))
            asyncio.create_task(remove_after_some_time(
                msg.bot, msg.chat, msg.message_id))
            return

        sqlParams = (msg.chat.id, msg.reply_to_message.message_id)
        sql = f"SELECT * FROM {Post.__tablename__} WHERE {Post.ChatId} = @ChatId AND {Post.MessageId} = @MessageId"

        post = db_connection.execute(sql, sqlParams).fetchone()

        if (post == None):
            m = await msg.bot.send_message(msg.chat.id, "Это сообщение нельзя удалить")
            asyncio.create_task(remove_after_some_time(
                msg.bot, msg.chat, m.message_id))
            asyncio.create_task(remove_after_some_time(
                msg.bot, msg.chat, msg.message_id))
            return

        if msg.from_user is None:
            return

        if (post[2] != msg.from_user.id):
            m = await msg.bot.send_message(msg.chat.id, "Нельзя удалить чужой пост")
            asyncio.create_task(remove_after_some_time(
                msg.bot, msg.chat, m.message_id))
            asyncio.create_task(remove_after_some_time(
                msg.bot, msg.chat, msg.message_id))
            return

        await msg.bot.delete_message(msg.chat.id, msg.reply_to_message.message_id)
        await msg.bot.delete_message(msg.chat.id, msg.message_id)
        sql = f"DELETE FROM {Interaction.__tablename__} WHERE {Interaction.ChatId} = @ChatId AND {Interaction.MessageId} = @MessageId;"
        db_connection.execute(sql, sqlParams)
        sql = f"DELETE FROM {Post.__tablename__} WHERE {Post.ChatId} = @ChatId AND {Post.MessageId} = @MessageId;"
        db_connection.execute(sql, sqlParams)

    except Exception as ex:
        print(ex, "Cannot handle media message")


async def HandleTextReplyAsync(msg: Message):
    logging.info("New valid text message")

    reply_to = msg.reply_to_message
    if reply_to is None:
        return

    from_user = reply_to.from_user
    if from_user is None:
        return

    new_message = await msg.bot.send_message(msg.chat.id, f"{AtMentionUsername(from_user)}:\n{reply_to.text}", reply_markup=new_post_ikm)
    await InsertIntoPosts(msg.chat.id, from_user.id, new_message.message_id)
    
    try:
        await msg.bot.delete_message(msg.chat.id, msg.message_id)
    except Exception as ex:  # TODO replace Exception
        logging.warning(
            ex, "Unable to delete message in HandleTextReplyAsync, duplicated update?")

    if (msg.from_user.id == from_user.id):
        await msg.bot.delete_message(chat_id=msg.chat.id, message_id=reply_to.message_id)

    


@router.message(Command(commands=["top_posts_day", "top_posts_week", "top_posts_month"]))
async def handle_top_week_posts(msg: Message):
    logging.info("Top posts")
    if(msg.text == None): return

    period=Period.Day

    if('top_posts_day' in str(msg.text)): period=Period.Day
    if('top_posts_week' in str(msg.text)): period=Period.Week
    if('top_posts_month' in str(msg.text)): period=Period.Month

    await HandleTopPosts(msg, period)


@router.message(Command(commands=["top_authors_day", "top_authors_week", "top_authors_month"]))
async def handle_top_authors_month(msg: Message):
    logging.info("Top authors")
    if(msg.text == None): return

    period=Period.Day

    if('top_authors_day' in str(msg.text)): period=Period.Day
    if('top_authors_week' in str(msg.text)): period=Period.Week
    if('top_authors_month' in str(msg.text)): period=Period.Month

    await HandleTopAuthors(msg, period)


async def HandleTopPosts(msg: Message, period: Period):
    chat = msg.chat
    if (chat.type != ChatType.SUPERGROUP and (not chat.username or chat.username.isspace())):
        await msg.bot.send_message(chat, "Этот чат не является супергруппой и не имеет имени: нет возможности оставлять ссылки на посты")
        logging.info(
            f"{(HandleTopPosts)} - unable to link top posts, skipping")
        return

    time_ago = (datetime.utcnow() - period.value).timestamp()

    sql_params = {'TimeAgo': time_ago, 'ChatId': chat.id}
    sql = GetMessageIdPlusCountPosterIdSql()
    plus_query = pd.read_sql_query(sql, db_connection, params=sql_params)

    plus = dict(zip(plus_query['MessageId'], plus_query['COUNT(*)']))
    messageIdToUserId = dict(
        zip(plus_query['MessageId'], plus_query['PosterId']))

    # Если нет плюсов, отправляем сообщение и завершаем выполнение
    if not plus:
        await msg.bot.send_message(chat.id, f"Не найдено заплюсованных постов за {ForLast(period)}")
        logging.info(f"handle_top_week_posts - no upvoted posts, skipping")
        return

    # Запрос для получения минусов
    sql = GetMessageIdMinusCountSql()

    minus_query = pd.read_sql_query(sql, db_connection, params=sql_params)

    minus = dict(zip(minus_query['MessageId'], minus_query['COUNT(*)']))

    # Вычитаем минусы из плюсов
    keys = list(plus.keys())
    for key in keys:
        plus[key] -= minus.get(key, 0)

    # Сортируем по убыванию и берем топ-20
    top_posts = sorted(plus.items(), key=lambda x: x[1], reverse=True)[:20]

    userIds = list(x[1] for x in messageIdToUserId.items())
    userIdToUser = await GetTelegramUsers(chat, userIds)


    message = f"Топ постов за {ForLast(period)}:\n"

    sg = chat.type == ChatType.SUPERGROUP
    for i, item in enumerate(top_posts):
        plus_symb = '\+'

        

        userMentition = "покинувшего чат пользователя"
        try:
            userId = messageIdToUserId[item[0]]
            user = userIdToUser[userId]
            userMentition = UserEscaped(user)
        except Exception as e:
            logging.error('User not exist')
            pass

        link = link_to_supergroup_message(
            chat, item[0]) if sg else link_to_group_with_name_message(chat, item[0])
        message += f"{GetPlace(i)} [От {userMentition}]({link}) "
        message += f"{plus_symb if item[1] > 0 else ''}{item[1]}\n"

    # Отправляем сообщение
    m = await msg.bot.send_message(chat.id, message, parse_mode=ParseMode.MARKDOWN_V2)

    asyncio.create_task(remove_after_some_time(msg.bot, chat, m.message_id))
    asyncio.create_task(remove_after_some_time(msg.bot, chat, msg.message_id))


async def HandleTopAuthors(msg: Message, period: Period):
    chat = msg.chat
    if (chat.type != ChatType.SUPERGROUP and (not chat.username or chat.username.isspace())):
        await msg.bot.send_message(chat, "Этот чат не является супергруппой и не имеет имени: нет возможности оставлять ссылки на посты")
        logging.info(
            f"{(HandleTopAuthors)} - unable to link top autors, skipping")
        return

    month_ago = (datetime.utcnow() - period.value).timestamp()

    sql_params = {'TimeAgo': month_ago, 'ChatId': chat.id}
    sql = GetMessageIdPlusCountPosterIdSql()
    plus_query = pd.read_sql_query(sql, db_connection, params=sql_params)

    plus = dict(zip(plus_query['MessageId'], plus_query['COUNT(*)']))

    # Если нет плюсов, отправляем сообщение и завершаем выполнение
    if not plus:
        await msg.bot.send_message(chat.id, f"Не найдено заплюсованных постов за {ForLast(period)}")
        logging.info(f"handle_top_month_authors - no upvoted posts, skipping")
        return

    # Группировка данных и подсчет H-индекса
    grouped_data = {}
    for poster_id, group in plus_query.groupby('PosterId'):
        h_index = sum(plus_count >= i + 1 for i,
                      plus_count in enumerate(sorted(group['COUNT(*)'], reverse=True)))
        likes = sum(group['COUNT(*)'])
        grouped_data[poster_id] = {'Key': poster_id,
                                   'Hindex': h_index, 'Likes': likes}

    # Сортировка и взятие топ-20
    top_authors = sorted(grouped_data.values(), key=lambda x: (
        x['Hindex'], x['Likes']), reverse=True)[:20]
    
    userIds = list(x['Key'] for x in top_authors)
    userIdToUser = await GetTelegramUsers(chat, userIds)

    message = f"Топ авторов за {ForLast(period)}:\n"

    for i, item in enumerate(top_authors):
        userMentition = "покинувший чат пользователь"
        try:
            user = userIdToUser[item['Key']]
            userMentition = UserEscaped(user)
        except Exception as e:
            logging.error('User not exist')
            pass
        message += f"{GetPlace(i)} {userMentition} очков: {item['Hindex']}, апвоутов: {item['Likes']}\n"

    # Отправляем сообщение
    m = await msg.bot.send_message(chat.id, message, parse_mode=ParseMode.MARKDOWN_V2)

    asyncio.create_task(remove_after_some_time(msg.bot, chat, m.message_id))
    asyncio.create_task(remove_after_some_time(msg.bot, chat, msg.message_id))

should_be_skipped = F.caption.lower().contains('/skip') | F.caption.lower().contains('#skip') | F.caption.lower().contains('/ignore') | F.caption.lower().contains('#ignore')


# Skipper Media
@router.message(should_be_skipped)
async def handle_media_message(msg: Message):
    logging.info("Media message that should be ignored")


# Skipper Album
@router.message(should_be_skipped)
async def handle_media_message(msg: Message, album: Album):
    logging.info("Media album message that should be ignored")

@router.message(F.media_group_id.is_(None), (F.photo | F.video))
@router.message(F.media_group_id.is_(None), F.document.mime_type.startswith('image') | F.document.mime_type.startswith('video'))
async def handle_media_message(msg: Message):
    logging.info("New valid media message")
    from_user = msg.from_user
    if (from_user is None):
        return

    if (msg.reply_to_message != None):
        logging.info("Reply media messages should be ignored")
        return
    

    try:
        new_message = await msg.bot.copy_message(chat_id=msg.chat.id, from_chat_id=msg.chat.id, message_id=msg.message_id,
                                                 reply_markup=new_post_ikm, caption=GenerateCaption(from_user, msg.caption), parse_mode=ParseMode.MARKDOWN_V2)
        await InsertIntoPosts(msg.chat.id, from_user.id, new_message.message_id)
        
        await msg.bot.delete_message(chat_id=msg.chat.id, message_id=msg.message_id)
    except Exception as ex:
        print(ex, "Cannot handle media message")

# @router.message(F.media_group_id, F.from_user[F.is_bot.is_(False)], (F.caption.contains('/skip') | F.caption.contains('#skip') | F.caption.contains('/ignore') | F.caption.contains('#ignore').is_(False)), flags={"throttling_key": "album"})
# @router.message(F.media_group_id, F.from_user[F.is_bot.is_(False)], (F.caption.contains('/skip') | F.caption.contains('#skip') | F.caption.contains('/ignore') | F.caption.contains('#ignore').is_(False)))
@router.message(F.media_group_id)
async def handle_media_group(msg: Message, album: Album):
    logging.info("New valid media group")

    from_user = msg.from_user
    if(from_user == None): return

    try:
        new_message = await msg.bot.send_message(msg.chat.id, "Оценить альбом", reply_to_message_id = msg.message_id, reply_markup = new_post_ikm)
        await InsertIntoPosts(msg.chat.id, from_user.id, new_message.message_id)
        
    except Exception as ex:
        logging.error(ex, "Cannot handle media group")



async def InsertIntoPosts(chat_id: int, poster_id: int, message_id: int):
    try:
        with db_connection:
            sql = f"INSERT INTO {Post.__tablename__} (ChatId, PosterId, MessageId, Timestamp) VALUES ( ?, ?, ?, ?);"
            cursor = db_connection.cursor()
            cursor.execute(sql, (chat_id, poster_id, message_id,
                           datetime.utcnow().timestamp()))
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


def link_to_supergroup_message(chat: Chat, message_id: int):
    return f"https://t.me/c/{str(chat.id)[4:]}/{message_id}"


def link_to_group_with_name_message(chat: Chat, message_id: int):
    return f"https://t.me/{chat.username}/{message_id}"


tt_re = r'^.*https:\/\/(?:m|www|vm)?\.?tiktok\.com\/((?:.*\b(?:(?:usr|v|embed|user|video)\/|\?shareId=|\&item_id=)(\d+))|\w+)'
@router.message(F.text.regexp(tt_re))
async def tiktok_handler(msg: Message):
    # Send a message indicating that the video is being downloaded
    tt_re_link = r'https:\/\/(?:m|www|vm)?\.?tiktok\.com\/((?:.*\b(?:(?:usr|v|embed|user|video)\/|\?shareId=|\&item_id=)(\d+))|\w+)'
    link = re.search(tt_re_link, msg.text, re.I)[0]
    text = msg.text.split(link)[0]
    try:
        await msg.bot.delete_message(msg.chat.id, msg.message_id)
        await msg.bot.send_chat_action(msg.chat.id, action=ChatAction.RECORD_VIDEO_NOTE)
        video_file_path = await run_yt_dlp(link)
        if(video_file_path == ''): return
        await msg.bot.send_chat_action(msg.chat.id, action=ChatAction.UPLOAD_VIDEO)
        new_message = await msg.bot.send_video(
            msg.chat.id,
            video=types.FSInputFile(path=video_file_path),
            caption=GenerateCaption(msg.from_user, text),
            disable_notification=True,
            reply_markup=new_post_ikm,
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        await InsertIntoPosts(msg.chat.id, msg.from_user.id, new_message.message_id)
    except Exception as e:
        logging.exception(f"Exception during answer_video: {e}")
    finally:
        os.remove(video_file_path)

    


def GenerateCaption(user: User | None, text: str | None) -> str:
    mention = MentionUsername(user)
    if (text != None and text != ''):
        return f"{mention}:\n\n{text}"
    return mention

def MentionUsername(from_user: User | None) -> str:
    whoEscaped = UserEscaped(from_user)
    return f"[От {whoEscaped}](tg://user?id={from_user.id})"


def UserEscaped(from_user: User | None) -> str:
    _should_be_escaped = set('_*[]()~`>#+-=|{}.!')

    who = GetFirstLastName(from_user)
    who_escaped = ''

    for c in who:
        if c in _should_be_escaped:
            who_escaped += '\\'
        who_escaped += c

    return str(who_escaped)


def AtMentionUsername(from_user: User | None) -> str:
    if (not from_user.username or from_user.username.isspace()):
        who = GetFirstLastName(from_user)
        return f"От {who} без ника в телеге"
    return f"От @{from_user.username}"


def GetFirstLastName(from_user: User | None) -> str:
    first_name = from_user.first_name or ""
    last_name = from_user.last_name or ""
    who = f"{first_name} {last_name}".strip()

    if (not who or who.isspace()):
        who = "анонима"
    return who

async def GetTelegramUsers(chat: Chat, userIds: list) -> dict:
    userIdToUser = {}
    for userId in userIds:
        try:
            member = await chat.bot.get_chat_member(chat.id, userId)
            userIdToUser[userId] = member.user
        except Exception as e:
            logging.error(e, "GetTelegramUsers")
            # User not found for any reason, we don't care.
            pass
    return userIdToUser
        

async def remove_after_some_time(bot_client: Bot, chat: Chat, message_id):
    await asyncio.sleep(10 * 60)  # Подождать 10 минут
    await bot_client.delete_message(chat.id, message_id)


def GetPlace(i: int) -> str:
    return {0: '🥇', 1: '🥈', 2: '🥉'}.get(i, f" {i + 1}")


async def main() -> None:
    global bot_id
    await init_and_migrate_db()
    bot = Bot(token=bot_token)
    bot_id = (await bot.get_me()).id
    dp = Dispatcher()
    dp.message.middleware(AlbumMiddleware())
    dp.include_routers(router)
    logging.info('bot started')
    await dp.start_polling(bot, skip_updates=True)


# Start the bot
if __name__ == '__main__':
    asyncio.run(main())
