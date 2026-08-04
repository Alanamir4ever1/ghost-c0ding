#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
GH0ST CODING — Бот для заказа разработки ботов
Версия: 2.3 (сроки принимаются любые, все функции работают)
"""

import asyncio
import csv
import io
import logging
import re
import sqlite3
import time
from datetime import datetime
from typing import Dict, List, Optional

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

# ===================== НАСТРОЙКИ =====================
BOT_TOKEN = "8843530914:AAEauug0xhKEUK-I1HxJhqVO0X9syXG2E0Q"
OWNER_ID = 6707650091
DB_PATH = "bots_orders.db"
PORTFOLIO_TEXT = (
    "📁 *Портфолио GH0ST CODING*\n\n"
    "Я разрабатываю Telegram-ботов для бизнеса. Вот несколько примеров:\n\n"
    "🛒 *E-commerce бот* — интернет-магазин с корзиной, оплатой и уведомлениями.\n"
    "💬 *Чат-бот поддержки* — автоматические ответы, опросы, обратная связь.\n"
    "📊 *CRM-бот* — управление клиентами, заявками, интеграция с Google Sheets.\n"
    "🔐 *Административный бот* — управление сотрудниками, отчёты, задачи.\n\n"
    "Свяжитесь со мной, чтобы обсудить ваш проект! 👻"
)

# ===================== ЛОГИРОВАНИЕ =====================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ===================== ИНИЦИАЛИЗАЦИЯ =====================
storage = MemoryStorage()
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=storage)

# ===================== БАЗА ДАННЫХ =====================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS bot_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            user_name TEXT NOT NULL,
            phone TEXT NOT NULL,
            bot_type TEXT NOT NULL,
            bot_name TEXT NOT NULL,
            description TEXT NOT NULL,
            budget INTEGER NOT NULL,
            deadline TEXT NOT NULL,
            timestamp INTEGER NOT NULL,
            status TEXT DEFAULT 'Новая',
            notified BOOLEAN DEFAULT 0
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS blacklist (
            user_id INTEGER PRIMARY KEY,
            reason TEXT,
            created_at INTEGER
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            order_id INTEGER NOT NULL,
            rating INTEGER NOT NULL,
            text TEXT,
            created_at INTEGER
        )
    """)
    c.execute("PRAGMA table_info(bot_orders)")
    columns = [col[1] for col in c.fetchall()]
    if "status" not in columns:
        c.execute("ALTER TABLE bot_orders ADD COLUMN status TEXT DEFAULT 'Новая'")
    conn.commit()
    conn.close()
    logger.info("База данных инициализирована")

# ---------- Функции БД ----------
def is_user_banned(user_id: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT 1 FROM blacklist WHERE user_id = ?", (user_id,))
    res = c.fetchone()
    conn.close()
    return bool(res)

def ban_user(user_id: int, reason: str = ""):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO blacklist (user_id, reason, created_at) VALUES (?, ?, ?)",
              (user_id, reason, int(time.time())))
    conn.commit()
    conn.close()

def unban_user(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM blacklist WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def get_blacklist():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id, reason, created_at FROM blacklist ORDER BY created_at DESC")
    rows = c.fetchall()
    conn.close()
    return rows

def save_order(user_id, user_name, phone, bot_type, bot_name, description, budget, deadline):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    ts = int(time.time())
    c.execute("""
        INSERT INTO bot_orders (user_id, user_name, phone, bot_type, bot_name, description, budget, deadline, timestamp, status, notified)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Новая', 0)
    """, (user_id, user_name, phone, bot_type, bot_name, description, budget, deadline, ts))
    order_id = c.lastrowid
    conn.commit()
    conn.close()
    return order_id

def get_order(order_id: int) -> Optional[Dict]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT id, user_id, user_name, phone, bot_type, bot_name, description, budget, deadline, timestamp, status
        FROM bot_orders WHERE id = ?
    """, (order_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            "id": row[0], "user_id": row[1], "user_name": row[2], "phone": row[3],
            "bot_type": row[4], "bot_name": row[5], "description": row[6],
            "budget": row[7], "deadline": row[8], "timestamp": row[9], "status": row[10]
        }
    return None

def get_orders_by_status(status: str) -> List[Dict]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT id, user_id, user_name, phone, bot_type, bot_name, description, budget, deadline, timestamp, status
        FROM bot_orders WHERE status = ? ORDER BY timestamp DESC
    """, (status,))
    rows = c.fetchall()
    conn.close()
    return [{
        "id": r[0], "user_id": r[1], "user_name": r[2], "phone": r[3],
        "bot_type": r[4], "bot_name": r[5], "description": r[6],
        "budget": r[7], "deadline": r[8], "timestamp": r[9], "status": r[10]
    } for r in rows]

def get_all_orders(limit=100):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT id, user_id, user_name, phone, bot_type, bot_name, description, budget, deadline, timestamp, status
        FROM bot_orders ORDER BY timestamp DESC LIMIT ?
    """, (limit,))
    rows = c.fetchall()
    conn.close()
    return [{
        "id": r[0], "user_id": r[1], "user_name": r[2], "phone": r[3],
        "bot_type": r[4], "bot_name": r[5], "description": r[6],
        "budget": r[7], "deadline": r[8], "timestamp": r[9], "status": r[10]
    } for r in rows]

def update_order_status(order_id: int, new_status: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE bot_orders SET status = ? WHERE id = ?", (new_status, order_id))
    updated = c.rowcount > 0
    conn.commit()
    conn.close()
    return updated

def get_user_orders(user_id, limit=10):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT id, user_name, phone, bot_type, bot_name, description, budget, deadline, timestamp, status
        FROM bot_orders WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?
    """, (user_id, limit))
    rows = c.fetchall()
    conn.close()
    return [{
        "id": r[0], "user_name": r[1], "phone": r[2], "bot_type": r[3],
        "bot_name": r[4], "description": r[5], "budget": r[6],
        "deadline": r[7], "timestamp": r[8], "status": r[9]
    } for r in rows]

def get_all_orders_count():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM bot_orders")
    count = c.fetchone()[0] or 0
    conn.close()
    return count

def get_today_stats():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    today_start = int(datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    c.execute("SELECT COUNT(*) FROM bot_orders WHERE timestamp >= ?", (today_start,))
    count = c.fetchone()[0] or 0
    c.execute("SELECT AVG(rating) FROM reviews")
    avg = c.fetchone()[0]
    conn.close()
    return {"count": count, "avg_rating": avg if avg else 0}

def mark_order_notified(order_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE bot_orders SET notified = 1 WHERE id = ?", (order_id,))
    conn.commit()
    conn.close()

def save_review(user_id, order_id, rating, text):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO reviews (user_id, order_id, rating, text, created_at) VALUES (?, ?, ?, ?, ?)",
              (user_id, order_id, rating, text, int(time.time())))
    conn.commit()
    conn.close()

def get_reviews(limit=50):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, user_id, order_id, rating, text, created_at FROM reviews ORDER BY created_at DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "user_id": r[1], "order_id": r[2], "rating": r[3], "text": r[4], "created_at": r[5]} for r in rows]

# ===================== ТИПЫ БОТОВ =====================
BOT_TYPES = {
    "ecom": {"name": "🛒 E-commerce", "price": "от 30 000 ₸", "short": "🛒 E-commerce"},
    "chat": {"name": "💬 Чат-бот", "price": "от 15 000 ₸", "short": "💬 Чат-бот"},
    "crm": {"name": "📊 CRM-система", "price": "от 50 000 ₸", "short": "📊 CRM"},
    "admin": {"name": "🔐 Административный бот", "price": "от 25 000 ₸", "short": "🔐 Админ-бот"},
    "custom": {"name": "🎨 Кастомный бот", "price": "договорная", "short": "🎨 Кастомный"},
}

# ===================== FSM =====================
class OrderForm(StatesGroup):
    waiting_phone = State()
    waiting_bot_type = State()
    waiting_bot_name = State()
    waiting_description = State()
    waiting_budget = State()
    waiting_deadline = State()

class OwnerReplyState(StatesGroup):
    waiting_for_message = State()

class ReviewState(StatesGroup):
    waiting_rating = State()
    waiting_text = State()

# ===================== ХРАНИЛИЩА =====================
chat_map = {}
clients = {}

# ===================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====================
def get_bot_types_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=data["short"], callback_data=f"bottype_{key}")] for key, data in BOT_TYPES.items()]
    )

def get_start_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Сделать заказ", callback_data="start_order")],
            [InlineKeyboardButton(text="📜 Мои заявки", callback_data="my_orders")],
            [InlineKeyboardButton(text="📁 Портфолио", callback_data="portfolio")],
        ]
    )

def get_bot_type_display(key):
    data = BOT_TYPES.get(key)
    return f"{data['name']} ({data['price']})" if data else key

def get_order_status_display(status: str) -> str:
    emojis = {"Новая": "🆕", "В работе": "🔄", "Готова": "✅", "Отменена": "❌"}
    return f"{emojis.get(status, '')} {status}"

def get_admin_orders_keyboard(orders: List[Dict], prefix: str = "admin_order_"):
    buttons = []
    for o in orders:
        buttons.append([InlineKeyboardButton(text=f"№{o['id']} – {o['user_name']}", callback_data=f"{prefix}{o['id']}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_order_detail_keyboard(order_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 В работу", callback_data=f"setstatus_{order_id}_В работе")],
            [InlineKeyboardButton(text="✅ Готова", callback_data=f"setstatus_{order_id}_Готова")],
            [InlineKeyboardButton(text="❌ Отменена", callback_data=f"setstatus_{order_id}_Отменена")],
            [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete_order_{order_id}")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")],
        ]
    )

# ===================== КОМАНДЫ =====================
@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_name = message.from_user.full_name or "гость"
    if is_user_banned(message.from_user.id):
        await message.answer("⛔ Ваш доступ заблокирован. Свяжитесь с разработчиком: @alanamir4ever")
        return
    text = (
        f"👻 *GH0ST CODING — разработка ботов для бизнеса*\n\n"
        f"Привет, {user_name}! 💻\n"
        "Я помогу вам создать бота под ваши задачи.\n\n"
        "🚀 *Что я умею:*\n"
        "• Интернет-магазины\n"
        "• Чат-боты для клиентов\n"
        "• CRM-системы\n"
        "• Административные боты\n"
        "• Кастомные решения\n\n"
        "📌 *Команды:*\n"
        "/start – это сообщение\n"
        "/help – помощь\n"
        "/support – контакты\n"
        "/status – статус заявок\n"
        "/portfolio – портфолио\n"
        "/cancel – отменить заявку\n\n"
        "👇 Нажмите кнопку ниже, чтобы начать!"
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=get_start_keyboard())
    logger.info(f"Команда /start от {message.from_user.id}")

@dp.message(Command("help"))
async def cmd_help(message: Message):
    if is_user_banned(message.from_user.id):
        await message.answer("⛔ Вы заблокированы.")
        return
    text = (
        "❓ *Как сделать заказ:*\n\n"
        "1. Нажмите «Сделать заказ» или /order.\n"
        "2. Выберите тип бота.\n"
        "3. Введите название, описание, бюджет и сроки.\n"
        "4. Подтвердите заявку.\n\n"
        "После отправки я свяжусь с вами.\n\n"
        "👻 *GH0ST CODING* — ваши боты, наш код."
    )
    await message.answer(text, parse_mode="Markdown")

@dp.message(Command("support"))
async def cmd_support(message: Message):
    await message.answer(
        "📞 *Контакты разработчика*\n\n"
        "👻 *GH0ST CODING*\n"
        "📱 Telegram: @alanamir4ever\n"
        "💬 По всем вопросам обращайтесь.",
        parse_mode="Markdown"
    )

@dp.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    current = await state.get_state()
    if current is None:
        await message.answer("❌ Нет активной заявки.", reply_markup=get_start_keyboard())
        return
    await state.clear()
    await message.answer("❌ Оформление заявки отменено.", reply_markup=get_start_keyboard())

@dp.message(Command("order"))
async def cmd_order(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if is_user_banned(user_id):
        await message.answer("⛔ Вы заблокированы.")
        return
    if await state.get_state() is not None:
        await message.answer("⚠️ Вы уже оформляете заявку. Используйте /cancel.")
        return
    await message.answer("📞 *Введите ваш номер телефона* (например, +77001234567):", parse_mode="Markdown")
    await state.set_state(OrderForm.waiting_phone)

@dp.message(Command("portfolio"))
async def cmd_portfolio(message: Message):
    await message.answer(PORTFOLIO_TEXT, parse_mode="Markdown")

@dp.message(Command("status"))
async def cmd_status(message: Message):
    user_id = message.from_user.id
    if is_user_banned(user_id):
        await message.answer("⛔ Вы заблокированы.")
        return
    orders = get_user_orders(user_id, 10)
    if not orders:
        await message.answer("📭 У вас ещё нет заявок.")
        return
    text = "📊 *Статусы заявок:*\n\n"
    for o in orders:
        text += f"№{o['id']} – *{get_bot_type_display(o['bot_type'])}*\n"
        text += f"Статус: {get_order_status_display(o['status'])}\n"
        text += f"⏱ Сроки: {o['deadline']}\n"
        text += f"📅 {datetime.fromtimestamp(o['timestamp']).strftime('%d.%m.%Y %H:%M')}\n\n"
    await message.answer(text, parse_mode="Markdown")

# ===================== АДМИН-КОМАНДЫ =====================
@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id != OWNER_ID:
        return
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🆕 Новые", callback_data="admin_list_new")],
            [InlineKeyboardButton(text="🔄 В работе", callback_data="admin_list_work")],
            [InlineKeyboardButton(text="✅ Готовые", callback_data="admin_list_done")],
            [InlineKeyboardButton(text="📊 Все", callback_data="admin_list_all")],
            [InlineKeyboardButton(text="⭐ Отзывы", callback_data="admin_reviews")],
            [InlineKeyboardButton(text="📥 Экспорт CSV", callback_data="admin_export")],
        ]
    )
    await message.answer("👑 *Админ-панель*", parse_mode="Markdown", reply_markup=keyboard)

@dp.message(Command("reviews"))
async def cmd_reviews(message: Message):
    if message.from_user.id != OWNER_ID:
        return
    reviews = get_reviews(20)
    if not reviews:
        await message.answer("📭 Отзывов пока нет.")
        return
    text = "⭐ *Отзывы:*\n\n"
    for r in reviews:
        dt = datetime.fromtimestamp(r["created_at"]).strftime("%d.%m.%Y %H:%M")
        text += f"№{r['order_id']} – {'⭐' * r['rating']}\n{r['text']}\n{dt}\n\n"
    await message.answer(text, parse_mode="Markdown")

@dp.message(Command("export"))
async def cmd_export(message: Message):
    if message.from_user.id != OWNER_ID:
        return
    orders = get_all_orders(1000)
    if not orders:
        await message.answer("Нет данных.")
        return
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Клиент", "Телефон", "Тип", "Название", "Описание", "Бюджет", "Сроки", "Статус", "Дата"])
    for o in orders:
        writer.writerow([
            o["id"], o["user_name"], o["phone"],
            get_bot_type_display(o["bot_type"]), o["bot_name"],
            o["description"], o["budget"], o["deadline"],
            o["status"], datetime.fromtimestamp(o["timestamp"]).strftime("%Y-%m-%d %H:%M")
        ])
    csv_bytes = output.getvalue().encode("utf-8")
    await message.answer_document(document=("orders_export.csv", csv_bytes), caption="📊 Экспорт заявок")

@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    if message.from_user.id != OWNER_ID:
        return
    total = get_all_orders_count()
    today = get_today_stats()
    text = (
        f"📊 *Статистика*\n\n"
        f"📦 Всего заявок: {total}\n"
        f"📆 За сегодня: {today['count']}\n"
        f"⭐ Средний рейтинг: {today['avg_rating']:.1f}\n\n"
        f"👻 *GH0ST CODING*"
    )
    await message.answer(text, parse_mode="Markdown")

@dp.message(Command("ban"))
async def cmd_ban(message: Message):
    if message.from_user.id != OWNER_ID:
        return
    parts = message.text.split(maxsplit=2)
    if len(parts) < 2:
        await message.answer("❌ /ban ID [причина]")
        return
    try:
        uid = int(parts[1])
    except ValueError:
        await message.answer("❌ ID должен быть числом.")
        return
    reason = parts[2] if len(parts) > 2 else ""
    if is_user_banned(uid):
        await message.answer(f"⚠️ Пользователь {uid} уже в чёрном списке.")
        return
    ban_user(uid, reason)
    await message.answer(f"✅ Пользователь {uid} заблокирован.")

@dp.message(Command("unban"))
async def cmd_unban(message: Message):
    if message.from_user.id != OWNER_ID:
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("❌ /unban ID")
        return
    try:
        uid = int(parts[1])
    except ValueError:
        await message.answer("❌ ID должен быть числом.")
        return
    if not is_user_banned(uid):
        await message.answer(f"⚠️ Пользователь {uid} не в чёрном списке.")
        return
    unban_user(uid)
    await message.answer(f"✅ Пользователь {uid} разблокирован.")

@dp.message(Command("blacklist"))
async def cmd_blacklist(message: Message):
    if message.from_user.id != OWNER_ID:
        return
    rows = get_blacklist()
    if not rows:
        await message.answer("📭 Чёрный список пуст.")
        return
    text = "🚫 *Чёрный список:*\n\n"
    for r in rows:
        dt = datetime.fromtimestamp(r[2]).strftime("%d.%m.%Y %H:%M")
        text += f"ID: {r[0]}\nПричина: {r[1] or 'не указана'}\nДобавлен: {dt}\n\n"
    await message.answer(text, parse_mode="Markdown")

# ===================== КОЛБЭКИ =====================
@dp.callback_query(F.data == "start_order")
async def start_order_cb(callback: CallbackQuery, state: FSMContext):
    if is_user_banned(callback.from_user.id):
        await callback.answer("⛔ Вы заблокированы.", show_alert=True)
        return
    if await state.get_state() is not None:
        await callback.answer("⚠️ У вас уже есть активная заявка.", show_alert=True)
        return
    await callback.message.answer("📞 *Введите ваш номер телефона* (например, +77001234567):", parse_mode="Markdown")
    await state.set_state(OrderForm.waiting_phone)
    await callback.answer()

@dp.callback_query(F.data == "my_orders")
async def my_orders_cb(callback: CallbackQuery):
    user_id = callback.from_user.id
    if is_user_banned(user_id):
        await callback.answer("⛔ Вы заблокированы.", show_alert=True)
        return
    orders = get_user_orders(user_id, 10)
    if not orders:
        await callback.message.answer("📭 У вас ещё нет заявок.")
        await callback.answer()
        return
    text = "📜 *Ваши заявки:*\n\n"
    for o in orders:
        dt = datetime.fromtimestamp(o["timestamp"]).strftime("%d.%m.%Y %H:%M")
        text += f"№{o['id']} – *{get_bot_type_display(o['bot_type'])}*\n"
        text += f"Статус: {get_order_status_display(o['status'])}\n"
        text += f"⏱ Сроки: {o['deadline']}\n"
        text += f"📅 {dt}\n\n"
    await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "portfolio")
async def portfolio_cb(callback: CallbackQuery):
    await callback.message.answer(PORTFOLIO_TEXT, parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data.startswith("bottype_"))
async def select_bot_type_cb(callback: CallbackQuery, state: FSMContext):
    bot_type = callback.data.split("_")[1]
    await state.update_data(bot_type=bot_type)
    await callback.message.answer(
        f"✅ Вы выбрали: *{get_bot_type_display(bot_type)}*\n\n"
        "📝 *Введите название бота* (или «нет»):",
        parse_mode="Markdown"
    )
    await state.set_state(OrderForm.waiting_bot_name)
    await callback.answer()

# ===================== FSM ЗАКАЗА =====================
@dp.message(OrderForm.waiting_phone)
async def process_phone(message: Message, state: FSMContext):
    if is_user_banned(message.from_user.id):
        await message.answer("⛔ Вы заблокированы.")
        await state.clear()
        return
    phone = message.text.strip().replace(" ", "")
    if not re.match(r'^\+?\d{10,15}$', phone):
        await message.answer("❌ Неверный формат. Пример: +77001234567")
        return
    await state.update_data(phone=phone)
    await message.answer("🤖 *Выберите тип бота:*", parse_mode="Markdown", reply_markup=get_bot_types_keyboard())
    await state.set_state(OrderForm.waiting_bot_type)

@dp.message(OrderForm.waiting_bot_name)
async def process_bot_name(message: Message, state: FSMContext):
    if is_user_banned(message.from_user.id):
        await message.answer("⛔ Вы заблокированы.")
        await state.clear()
        return
    name = message.text.strip()
    await state.update_data(bot_name=name)
    await message.answer("📋 *Опишите задачу:*", parse_mode="Markdown")
    await state.set_state(OrderForm.waiting_description)

@dp.message(OrderForm.waiting_description)
async def process_description(message: Message, state: FSMContext):
    if is_user_banned(message.from_user.id):
        await message.answer("⛔ Вы заблокированы.")
        await state.clear()
        return
    desc = message.text.strip()
    if len(desc) < 5:
        await message.answer("❌ Описание слишком короткое. Напишите подробнее.")
        return
    await state.update_data(description=desc)
    await message.answer("💰 *Укажите бюджет в тенге:*", parse_mode="Markdown")
    await state.set_state(OrderForm.waiting_budget)

@dp.message(OrderForm.waiting_budget)
async def process_budget(message: Message, state: FSMContext):
    if is_user_banned(message.from_user.id):
        await message.answer("⛔ Вы заблокированы.")
        await state.clear()
        return
    try:
        budget = int(message.text.strip().replace(" ", "").replace("₸", ""))
        if budget < 1000:
            await message.answer("❌ Минимальный бюджет — 1000 ₸.")
            return
    except ValueError:
        await message.answer("❌ Введите число, например: 30000")
        return
    await state.update_data(budget=budget)
    await message.answer("⏱ *Укажите желаемые сроки:*", parse_mode="Markdown")
    await state.set_state(OrderForm.waiting_deadline)

# ===================== ИСПРАВЛЕННЫЙ ОБРАБОТЧИК СРОКОВ (БЕЗ ПРОВЕРКИ ДЛИНЫ) =====================
@dp.message(OrderForm.waiting_deadline)
async def process_deadline(message: Message, state: FSMContext):
    if is_user_banned(message.from_user.id):
        await message.answer("⛔ Вы заблокированы.")
        await state.clear()
        return
    deadline = message.text.strip()
    if not deadline:
        await message.answer("❌ Напишите сроки.")
        return
    await state.update_data(deadline=deadline)

    # Получаем все данные
    data = await state.get_data()
    phone = data.get("phone")
    bot_type = data.get("bot_type")
    bot_name = data.get("bot_name")
    description = data.get("description")
    budget = data.get("budget")
    bot_type_display = get_bot_type_display(bot_type)

    confirm_text = (
        f"📦 *ПОДТВЕРЖДЕНИЕ ЗАЯВКИ*\n\n"
        f"📞 Телефон: {phone}\n"
        f"🤖 Тип: {bot_type_display}\n"
        f"📝 Название: {bot_name or 'не указано'}\n"
        f"📋 Описание:\n{description}\n"
        f"💰 Бюджет: {budget} ₸\n"
        f"⏱ Сроки: {deadline}\n\n"
        "✅ Всё верно?"
    )
    await message.answer(
        confirm_text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_bot_order")],
                [InlineKeyboardButton(text="✖️ Отменить", callback_data="cancel_bot_order")]
            ]
        )
    )

@dp.callback_query(F.data == "confirm_bot_order")
async def confirm_order_cb(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if is_user_banned(user_id):
        await callback.answer("⛔ Вы заблокированы.", show_alert=True)
        await state.clear()
        return
    data = await state.get_data()
    user_name = callback.from_user.full_name or "Пользователь"
    phone = data.get("phone")
    bot_type = data.get("bot_type")
    bot_name = data.get("bot_name")
    description = data.get("description")
    budget = data.get("budget")
    deadline = data.get("deadline")

    if not all([phone, bot_type, description, budget, deadline]):
        await callback.answer("❌ Ошибка: не все данные заполнены.", show_alert=True)
        await state.clear()
        return

    order_id = save_order(user_id, user_name, phone, bot_type, bot_name, description, budget, deadline)

    bot_type_display = get_bot_type_display(bot_type)
    owner_msg = (
        f"🆕 *НОВАЯ ЗАЯВКА!* (№{order_id})\n\n"
        f"👤 Клиент: {user_name} (ID: {user_id})\n"
        f"📞 Телефон: {phone}\n"
        f"🤖 Тип: {bot_type_display}\n"
        f"📝 Название: {bot_name or 'не указано'}\n"
        f"📋 Описание:\n{description}\n"
        f"💰 Бюджет: {budget} ₸\n"
        f"⏱ Сроки: {deadline}\n\n"
        f"👻 *GH0ST CODING* — новый заказ!"
    )
    try:
        await bot.send_message(OWNER_ID, owner_msg, parse_mode="Markdown")
        mark_order_notified(order_id)
    except Exception as e:
        logger.error(f"Не удалось отправить уведомление: {e}")

    await callback.message.edit_text(
        f"✅ *Спасибо, {user_name}!*\n\n"
        f"Ваша заявка №{order_id} принята!\n"
        f"Я свяжусь с вами в ближайшее время.\n\n"
        f"📋 Тип: {bot_type_display}\n"
        f"💰 Бюджет: {budget} ₸\n"
        f"⏱ Сроки: {deadline}\n\n"
        "👻 *GH0ST CODING* — ваши боты, наш код.",
        parse_mode="Markdown",
        reply_markup=get_start_keyboard()
    )
    await state.clear()
    await callback.answer()

@dp.callback_query(F.data == "cancel_bot_order")
async def cancel_order_cb(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("❌ Оформление заявки отменено.", reply_markup=get_start_keyboard())
    await state.clear()
    await callback.answer()

# ===================== АДМИН-КОЛБЭКИ =====================
@dp.callback_query(F.data.startswith("admin_list_"))
async def admin_list_cb(callback: CallbackQuery):
    if callback.from_user.id != OWNER_ID:
        await callback.answer("⛔ Нет прав", show_alert=True)
        return
    key = callback.data.split("_")[2]
    if key == "all":
        orders = get_all_orders(20)
        title = "Все заявки"
    else:
        status_map = {"new": "Новая", "work": "В работе", "done": "Готова"}
        status = status_map.get(key, "Новая")
        orders = get_orders_by_status(status)
        title = f"Заявки со статусом «{status}»"
    if not orders:
        await callback.message.edit_text(f"📭 {title} пусты.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]]))
        await callback.answer()
        return
    text = f"👑 *{title}*\n\n"
    for o in orders[:20]:
        text += f"№{o['id']} – {o['user_name']} | {get_bot_type_display(o['bot_type'])} | {get_order_status_display(o['status'])}\n"
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=get_admin_orders_keyboard(orders))
    await callback.answer()

@dp.callback_query(F.data.startswith("admin_order_"))
async def admin_order_detail(callback: CallbackQuery):
    if callback.from_user.id != OWNER_ID:
        await callback.answer("⛔ Нет прав", show_alert=True)
        return
    order_id = int(callback.data.split("_")[2])
    order = get_order(order_id)
    if not order:
        await callback.message.edit_text("❌ Заявка не найдена.")
        await callback.answer()
        return
    text = (
        f"📋 *Заявка №{order['id']}*\n\n"
        f"👤 Клиент: {order['user_name']} (ID: {order['user_id']})\n"
        f"📞 Телефон: {order['phone']}\n"
        f"🤖 Тип: {get_bot_type_display(order['bot_type'])}\n"
        f"📝 Название: {order['bot_name'] or 'не указано'}\n"
        f"📋 Описание:\n{order['description']}\n"
        f"💰 Бюджет: {order['budget']} ₸\n"
        f"⏱ Сроки: {order['deadline']}\n"
        f"📅 {datetime.fromtimestamp(order['timestamp']).strftime('%d.%m.%Y %H:%M')}\n"
        f"📌 Статус: {get_order_status_display(order['status'])}"
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=get_order_detail_keyboard(order_id))
    await callback.answer()

@dp.callback_query(F.data.startswith("setstatus_"))
async def set_status_cb(callback: CallbackQuery):
    if callback.from_user.id != OWNER_ID:
        await callback.answer("⛔ Нет прав", show_alert=True)
        return
    _, _, order_id, new_status = callback.data.split("_", 3)
    order_id = int(order_id)
    order = get_order(order_id)
    if not order:
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    update_order_status(order_id, new_status)
    try:
        if new_status == "Готова":
            await bot.send_message(
                order["user_id"],
                f"✅ *Заявка №{order_id} завершена!*\n\nСпасибо! 👻\nОцените работу:",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text="⭐ Оценить", callback_data=f"rate_{order_id}")]]
                )
            )
        else:
            await bot.send_message(
                order["user_id"],
                f"📌 *Статус заявки №{order_id} изменён*\nНовый: {get_order_status_display(new_status)}",
                parse_mode="Markdown"
            )
    except Exception as e:
        logger.error(f"Не удалось уведомить клиента: {e}")
    await callback.message.edit_text(f"✅ Статус заявки №{order_id} изменён на «{new_status}».")
    await admin_order_detail(callback)

@dp.callback_query(F.data.startswith("delete_order_"))
async def delete_order_cb(callback: CallbackQuery):
    if callback.from_user.id != OWNER_ID:
        await callback.answer("⛔ Нет прав", show_alert=True)
        return
    order_id = int(callback.data.split("_")[2])
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM bot_orders WHERE id = ?", (order_id,))
    conn.commit()
    conn.close()
    await callback.message.edit_text(f"🗑 Заявка №{order_id} удалена.")
    await callback.answer()

@dp.callback_query(F.data == "admin_back")
async def admin_back_cb(callback: CallbackQuery):
    if callback.from_user.id != OWNER_ID:
        await callback.answer("⛔ Нет прав", show_alert=True)
        return
    await cmd_admin(callback.message)

@dp.callback_query(F.data == "admin_reviews")
async def admin_reviews_cb(callback: CallbackQuery):
    if callback.from_user.id != OWNER_ID:
        await callback.answer("⛔ Нет прав", show_alert=True)
        return
    reviews = get_reviews(20)
    if not reviews:
        await callback.message.edit_text("📭 Отзывов пока нет.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")]]))
        await callback.answer()
        return
    text = "⭐ *Отзывы:*\n\n"
    for r in reviews:
        dt = datetime.fromtimestamp(r["created_at"]).strftime("%d.%m.%Y %H:%M")
        text += f"№{r['order_id']} – {'⭐' * r['rating']}\n{r['text']}\n{dt}\n\n"
    await callback.message.edit_text(text, parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "admin_export")
async def admin_export_cb(callback: CallbackQuery):
    if callback.from_user.id != OWNER_ID:
        await callback.answer("⛔ Нет прав", show_alert=True)
        return
    orders = get_all_orders(1000)
    if not orders:
        await callback.answer("Нет данных", show_alert=True)
        return
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Клиент", "Телефон", "Тип", "Название", "Описание", "Бюджет", "Сроки", "Статус", "Дата"])
    for o in orders:
        writer.writerow([
            o["id"], o["user_name"], o["phone"],
            get_bot_type_display(o["bot_type"]), o["bot_name"],
            o["description"], o["budget"], o["deadline"],
            o["status"], datetime.fromtimestamp(o["timestamp"]).strftime("%Y-%m-%d %H:%M")
        ])
    csv_bytes = output.getvalue().encode("utf-8")
    await callback.message.answer_document(document=("orders_export.csv", csv_bytes), caption="📊 Экспорт заявок")
    await callback.answer()

# ===================== ОЦЕНКИ =====================
@dp.callback_query(F.data.startswith("rate_"))
async def rate_cb(callback: CallbackQuery, state: FSMContext):
    if is_user_banned(callback.from_user.id):
        await callback.answer("⛔ Вы заблокированы.", show_alert=True)
        return
    order_id = int(callback.data.split("_")[1])
    order = get_order(order_id)
    if not order or order["user_id"] != callback.from_user.id:
        await callback.answer("Ошибка", show_alert=True)
        return
    await state.update_data(order_id=order_id)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⭐" * i, callback_data=f"rating_{i}") for i in range(1, 6)]]
    )
    await callback.message.answer("⭐ *Оцените работу от 1 до 5:*", parse_mode="Markdown", reply_markup=keyboard)
    await state.set_state(ReviewState.waiting_rating)
    await callback.answer()

@dp.callback_query(ReviewState.waiting_rating, F.data.startswith("rating_"))
async def rating_cb(callback: CallbackQuery, state: FSMContext):
    rating = int(callback.data.split("_")[1])
    await state.update_data(rating=rating)
    await callback.message.answer("✍️ *Напишите текстовый отзыв:*", parse_mode="Markdown")
    await state.set_state(ReviewState.waiting_text)
    await callback.answer()

@dp.message(ReviewState.waiting_text)
async def review_text(message: Message, state: FSMContext):
    text = message.text.strip()
    if not text:
        await message.answer("❌ Напишите отзыв.")
        return
    data = await state.get_data()
    save_review(message.from_user.id, data.get("order_id"), data.get("rating"), text)
    await message.answer("✅ Спасибо за отзыв! 👻")
    await state.clear()

# ===================== ПЕРЕСЫЛКА И АВТООТВЕТ =====================
@dp.message(F.text & ~F.command)
async def handle_any_text(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id == OWNER_ID:
        return
    current_state = await state.get_state()
    if current_state is not None:
        return
    if is_user_banned(user_id):
        await message.answer("⛔ Вы заблокированы. Свяжитесь с @alanamir4ever")
        return

    clients[user_id] = message.from_user.full_name or "Пользователь"

    forward_text = (
        f"💬 *Сообщение от клиента*\n"
        f"От: {message.from_user.full_name} (@{message.from_user.username or 'нет'})\n"
        f"ID: {user_id}\n\n"
        f"Текст:\n{message.text}"
    )
    try:
        sent_msg = await bot.send_message(OWNER_ID, forward_text, parse_mode="Markdown")
        chat_map[sent_msg.message_id] = user_id
        logger.info(f"Переслано от {user_id}")
    except Exception as e:
        logger.error(f"Не удалось переслать: {e}")

    await message.answer(
        "Привет! 👋 Я GH0ST CODING — разработчик ботов.\n"
        "Чтобы сделать заказ, нажмите «🚀 Сделать заказ» или /order.\n"
        "Если есть вопросы — пишите! 💬",
        reply_markup=get_start_keyboard()
    )

# ===================== ОТВЕТЫ ВЛАДЕЛЬЦА =====================
@dp.message(F.from_user.id == OWNER_ID, F.reply_to_message)
async def owner_reply(message: Message):
    replied_id = message.reply_to_message.message_id
    user_id = chat_map.pop(replied_id, None)
    if user_id is None:
        await message.reply("⚠️ Не удалось определить получателя.")
        return
    try:
        await bot.send_message(
            user_id,
            f"👻 *Ответ от разработчика:*\n\n{message.text}",
            parse_mode="Markdown"
        )
        await message.reply("✅ Ответ отправлен.")
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await message.reply("❌ Не удалось отправить.")

# ===================== /chatlist =====================
@dp.message(Command("chatlist"))
async def cmd_chatlist(message: Message):
    if message.from_user.id != OWNER_ID:
        return
    if not clients:
        await message.answer("📭 Список клиентов пуст.")
        return
    buttons = [[InlineKeyboardButton(text=n[:20], callback_data=f"reply_to_{uid}")] for uid, n in clients.items()]
    await message.answer("👥 *Клиенты:*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("reply_to_"))
async def select_client_cb(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != OWNER_ID:
        await callback.answer("⛔ Нет прав", show_alert=True)
        return
    uid = int(callback.data.split("_")[2])
    await state.update_data(target_user_id=uid)
    await state.set_state(OwnerReplyState.waiting_for_message)
    await callback.message.edit_text(f"✍️ *Напишите сообщение для {clients.get(uid, 'клиента')} (ID: {uid}):*", parse_mode="Markdown")
    await callback.answer()

@dp.message(OwnerReplyState.waiting_for_message, F.from_user.id == OWNER_ID)
async def send_owner_msg(message: Message, state: FSMContext):
    data = await state.get_data()
    target = data.get("target_user_id")
    if not target:
        await message.answer("❌ Не выбран клиент.")
        await state.clear()
        return
    try:
        await bot.send_message(target, f"👻 *Ответ от разработчика:*\n\n{message.text}", parse_mode="Markdown")
        await message.reply("✅ Ответ отправлен.")
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await message.reply("❌ Не удалось отправить.")
    await state.clear()

@dp.message(Command("cancel"), OwnerReplyState.waiting_for_message)
async def cancel_owner_reply(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID:
        return
    await state.clear()
    await message.answer("❌ Отправка отменена.")

# ===================== ЗАПУСК =====================
async def main():
    logger.info("Бот GH0ST CODING запускается...")
    init_db()
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())