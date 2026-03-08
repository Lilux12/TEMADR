#!/usr/bin/env python3
"""
🎂 Бот для голосования на день рождения Артёма!
День рождения: 4 апреля 2026 (13 лет!)
Админ: @Lilux12

Расписание раундов:
- Раунд 1:  8–17 марта  (голосуем за всё, остаётся ТОП-5)
- Раунд 2: 18–25 марта  (голосуем за ТОП-5, остаётся ТОП-3)
- Раунд 3: 26–31 марта  (голосуем за ТОП-3, остаётся победитель)
- 1 апреля 12:00 — результат летит только @Lilux12
"""

import logging
import json
import os
import datetime
from datetime import date

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

# ══════════════════════════════════════════════
#  НАСТРОЙКИ  ← ЗАПОЛНИ ЭТИ ДВЕ СТРОКИ
# ══════════════════════════════════════════════
BOT_TOKEN      = "ВСТАВЬ_СЮДА_ТОКЕН_БОТА"
BOT_USERNAME   = "ВСТАВЬ_ИМЯ_БОТА_БЕЗ_СОБАКИ"   # например: VoteArtomBot
ADMIN_USERNAME = "Lilux12"                         # без @
DATA_FILE      = "votes_data.json"

# ── Расписание раундов ──
ROUNDS = {
    1: {"start": date(2026, 3,  8), "end": date(2026, 3, 17), "keep": 5},
    2: {"start": date(2026, 3, 18), "end": date(2026, 3, 25), "keep": 3},
    3: {"start": date(2026, 3, 26), "end": date(2026, 3, 31), "keep": 1},
}
RESULT_DATE = date(2026, 4, 1)

# ── Стартовые варианты ──
INITIAL_OPTIONS = [
    {"id": "quest",    "name": "👻 Квест очень страшный (с актёрами)", "url": "https://quest5.ru/silent-hill"},
    {"id": "pakabata", "name": "🎮 Пакабата",                        "url": "https://pakabata-nn.ru/"},
    {"id": "karting",  "name": "🏎️ Картинг",                        "url": "https://zharptitsann.ru/karting"},
    {"id": "galileo",  "name": "🎡 Парк чудес Галилео",              "url": "https://nn.galileopark.ru/"},
    {"id": "bowling",  "name": "🎳 Боулинг",                         "url": None},
]

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════
#  ХРАНИЛИЩЕ
# ══════════════════════════════════════════════

def load_data() -> dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "round": 1,
        "options": {o["id"]: o for o in INITIAL_OPTIONS},
        "active_options": [o["id"] for o in INITIAL_OPTIONS],
        "votes": {},               # {"1": {"user_id": "opt_id"}, ...}
        "custom_suggestions": [],  # [{id, name, suggested_by}]
        "result_sent": False,
        "invite_counts": {},       # {"user_id": count}
        "invited_by": {},          # {"new_user_id": "inviter_user_id"}
    }


def save_data(data: dict):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ══════════════════════════════════════════════
#  УТИЛИТЫ
# ══════════════════════════════════════════════

def get_current_round() -> int:
    today = date.today()
    for r, info in ROUNDS.items():
        if info["start"] <= today <= info["end"]:
            return r
    return 4 if today >= RESULT_DATE else 0


def is_admin(update: Update) -> bool:
    return (update.effective_user.username or "").lower() == ADMIN_USERNAME.lower()


def get_vote_counts(data: dict, round_num: int) -> dict:
    r_votes = data["votes"].get(str(round_num), {})
    counts = {oid: 0 for oid in data["active_options"]}
    for _, oid in r_votes.items():
        if oid in counts:
            counts[oid] += 1
    return counts


def get_top_n(data: dict, round_num: int, n: int) -> list:
    counts = get_vote_counts(data, round_num)
    return [oid for oid, _ in sorted(counts.items(), key=lambda x: x[1], reverse=True)[:n]]


def get_user_vote(data: dict, user_id: str, round_num: int):
    return data["votes"].get(str(round_num), {}).get(user_id)


def round_status_text(round_num: int) -> str:
    if round_num == 0:
        s = ROUNDS[1]["start"]
        return f"⏳ Голосование стартует <b>{s.strftime('%d.%m')}</b>!"
    if round_num == 1:
        e = ROUNDS[1]["end"].strftime("%d.%m")
        return f"🔥 <b>Раунд 1</b> (до {e}) — голосуем за всё! Выйдет ТОП-5."
    if round_num == 2:
        e = ROUNDS[2]["end"].strftime("%d.%m")
        return f"🔥 <b>Раунд 2</b> (до {e}) — ТОП-5 бьётся! Выйдет ТОП-3."
    if round_num == 3:
        e = ROUNDS[3]["end"].strftime("%d.%m")
        return f"🏆 <b>Раунд 3</b> (до {e}) — финал! Будет один победитель."
    return "🎉 Голосование завершено!"


def build_vote_keyboard(data: dict, user_voted_id: str = None, admin: bool = False) -> InlineKeyboardMarkup:
    buttons = []
    for oid in data["active_options"]:
        opt = data["options"].get(oid)
        if not opt:
            continue
        mark = " ✔️" if oid == user_voted_id else ""
        row = [InlineKeyboardButton(f"{opt['name']}{mark}", callback_data=f"vote_{oid}")]
        if opt.get("url"):
            row.append(InlineKeyboardButton("🔗", url=opt["url"]))
        buttons.append(row)
    buttons.append([InlineKeyboardButton("✏️ Предложить свой вариант", callback_data="suggest_custom")])
    if admin:
        buttons.append([InlineKeyboardButton("🔐 Админ-панель", callback_data="admin_back")])
    return InlineKeyboardMarkup(buttons)


def build_vote_keyboard_with_counts(data: dict, round_num: int, user_voted_id: str = None, admin: bool = False) -> InlineKeyboardMarkup:
    counts = get_vote_counts(data, round_num)
    total = sum(counts.values()) or 1
    buttons = []
    for oid in data["active_options"]:
        opt = data["options"].get(oid)
        if not opt:
            continue
        cnt = counts.get(oid, 0)
        pct = round(cnt / total * 100)
        mark = " ✔️" if oid == user_voted_id else ""
        row = [InlineKeyboardButton(
            f"{opt['name']}{mark} — {cnt} ({pct}%)", callback_data=f"vote_{oid}"
        )]
        if opt.get("url"):
            row.append(InlineKeyboardButton("🔗", url=opt["url"]))
        buttons.append(row)
    buttons.append([InlineKeyboardButton("✏️ Предложить свой вариант", callback_data="suggest_custom")])
    if admin:
        buttons.append([InlineKeyboardButton("🔐 Админ-панель", callback_data="admin_back")])
    return InlineKeyboardMarkup(buttons)


# ══════════════════════════════════════════════
#  КОМАНДЫ
# ══════════════════════════════════════════════

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    user = update.effective_user
    user_id = str(user.id)

    # Обработка реферала: /start invite_123456789
    if context.args:
        arg = context.args[0]
        if arg.startswith("invite_"):
            inviter_id = arg.replace("invite_", "")
            if inviter_id != user_id and user_id not in data["invited_by"]:
                data["invited_by"][user_id] = inviter_id
                data["invite_counts"][inviter_id] = data["invite_counts"].get(inviter_id, 0) + 1
                save_data(data)
                try:
                    cnt = data["invite_counts"][inviter_id]
                    inviter_name = user.first_name or ("@" + user.username) if user.username else "Кто-то"
                    await context.bot.send_message(
                        int(inviter_id),
                        f"🎉 По твоей ссылке пришёл <b>{inviter_name}</b>!\n"
                        f"Ты уже позвал <b>{cnt}</b> чел. 🔥",
                        parse_mode="HTML"
                    )
                except Exception:
                    pass

    admin = is_admin(update)
    round_num = get_current_round()
    user_voted = get_user_vote(data, user_id, round_num) if round_num in (1, 2, 3) else None

    text = (
        f"🎂 <b>Привет, {user.first_name}!</b>\n"
        f"Голосуем куда пойти на ДР Артёма 🎉\n"
        f"🗓 <b>4 апреля 2026</b> — ему исполнится 13 лет!\n\n"
        f"{round_status_text(round_num)}\n"
    )

    if round_num in (1, 2, 3):
        if user_voted:
            opt_name = data["options"].get(user_voted, {}).get("name", "?")
            text += f"\n👆 Твой голос: <b>{opt_name}</b>\nМожно изменить 👇"
            keyboard = build_vote_keyboard_with_counts(data, round_num, user_voted, admin)
        else:
            text += "\n👇 Выбери вариант:"
            keyboard = build_vote_keyboard(data, user_voted, admin)
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)
    else:
        extra = InlineKeyboardMarkup([[InlineKeyboardButton("🔐 Админ-панель", callback_data="admin_back")]]) if admin else None
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=extra)


async def cmd_vote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_start(update, context)


async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update):
        await show_admin_menu(update, context)
    else:
        await update.message.reply_text("❌ Нет доступа.")


# ══════════════════════════════════════════════
#  ГОЛОСОВАНИЕ
# ══════════════════════════════════════════════

async def handle_vote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = load_data()
    round_num = get_current_round()

    if round_num not in (1, 2, 3):
        await query.answer("Голосование сейчас не активно!", show_alert=True)
        return

    opt_id = query.data.replace("vote_", "")
    if opt_id not in data["active_options"]:
        await query.answer("Этот вариант недоступен!", show_alert=True)
        return

    user_id = str(query.from_user.id)
    round_key = str(round_num)
    data["votes"].setdefault(round_key, {})

    prev = data["votes"][round_key].get(user_id)
    data["votes"][round_key][user_id] = opt_id
    save_data(data)

    opt_name = data["options"][opt_id]["name"]
    if prev and prev != opt_id:
        prev_name = data["options"].get(prev, {}).get("name", prev)
        msg = f"🔄 Изменил голос:\n«{prev_name}» → «{opt_name}»"
    else:
        msg = f"✅ Ты проголосовал за\n«{opt_name}»!"
    await query.answer(msg, show_alert=True)

    # Обновить клавиатуру со счётчиками
    await query.edit_message_reply_markup(
        reply_markup=build_vote_keyboard_with_counts(data, round_num, opt_id)
    )


# ══════════════════════════════════════════════
#  ПОДЕЛИТЬСЯ / ПОЗВАТЬ ОДНОКЛАССНИКА
# ══════════════════════════════════════════════

async def handle_share_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    invite_link = f"https://t.me/{BOT_USERNAME}?start=invite_{user_id}"

    # Ссылка для кнопки «Переслать» через Telegram share
    import urllib.parse
    share_text = urllib.parse.quote(
        "🎂 Проголосуй куда пойти на ДР Артёма 4 апреля!\n👇 Нажми и выбери вариант:"
    )
    share_url = f"https://t.me/share/url?url={urllib.parse.quote(invite_link)}&text={share_text}"

    data = load_data()
    my_count = data["invite_counts"].get(str(user_id), 0)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Переслать другу / одноклассникам", url=share_url)],
        [InlineKeyboardButton("◀️ Назад к голосованию", callback_data="back_to_vote")],
    ])

    await query.edit_message_text(
        f"👥 <b>Позови одноклассника!</b>\n\n"
        f"Отправь ему эту ссылку или нажми кнопку «Переслать»:\n\n"
        f"<code>{invite_link}</code>\n\n"
        f"Когда друг перейдёт — ты получишь уведомление 🔔\n"
        f"📨 По твоей ссылке пришло: <b>{my_count}</b> чел.",
        parse_mode="HTML",
        reply_markup=keyboard
    )


async def handle_back_to_vote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = load_data()
    round_num = get_current_round()
    user_id = str(query.from_user.id)
    user_voted = get_user_vote(data, user_id, round_num) if round_num in (1, 2, 3) else None

    text = f"{round_status_text(round_num)}\n"
    if round_num in (1, 2, 3):
        if user_voted:
            opt_name = data["options"].get(user_voted, {}).get("name", "?")
            text += f"\n👆 Твой голос: <b>{opt_name}</b>\nМожно изменить 👇"
            keyboard = build_vote_keyboard_with_counts(data, round_num, user_voted)
        else:
            text += "\n👇 Выбери вариант:"
            keyboard = build_vote_keyboard(data)
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)
    else:
        await query.edit_message_text(text, parse_mode="HTML")


# ══════════════════════════════════════════════
#  СВОЙ ВАРИАНТ
# ══════════════════════════════════════════════

async def handle_suggest_custom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["awaiting_suggestion"] = True
    await query.message.reply_text(
        "✏️ Напиши свой вариант одним сообщением.\n"
        "Например: «Верёвочный парк» или «Лазертаг»\n\n"
        "Он добавится в список для всех!"
    )


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_suggestion"):
        return
    context.user_data["awaiting_suggestion"] = False

    suggestion = update.message.text.strip()
    if not suggestion or len(suggestion) > 100:
        await update.message.reply_text("❌ Слишком длинный или пустой текст. Попробуй /vote")
        return

    data = load_data()
    custom_id = f"custom_{len(data['custom_suggestions']) + 1}"
    new_opt = {
        "id": custom_id,
        "name": f"💡 {suggestion}",
        "url": None,
        "suggested_by": update.effective_user.username or str(update.effective_user.id)
    }
    data["options"][custom_id] = new_opt
    data["active_options"].append(custom_id)
    data["custom_suggestions"].append(new_opt)
    save_data(data)

    user_id = str(update.effective_user.id)
    round_num = get_current_round()
    user_voted = get_user_vote(data, user_id, round_num) if round_num in (1, 2, 3) else None

    await update.message.reply_text(
        f"🎉 Вариант «{suggestion}» добавлен!\nТеперь за него можно голосовать 👇",
        reply_markup=build_vote_keyboard(data, user_voted)
    )


# ══════════════════════════════════════════════
#  АДМИН-ПАНЕЛЬ
# ══════════════════════════════════════════════

async def show_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    round_num = get_current_round()
    counts = get_vote_counts(data, round_num) if round_num in (1, 2, 3) else {}
    total_voters = len(data["votes"].get(str(round_num), {}))
    total_invited = sum(data.get("invite_counts", {}).values())

    text = (
        f"🔐 <b>АДМИН-ПАНЕЛЬ</b> — @{ADMIN_USERNAME}\n\n"
        f"📅 Сегодня: <b>{date.today().strftime('%d.%m.%Y')}</b>\n"
        f"🏁 Раунд: <b>{round_num if round_num in (1, 2, 3) else '—'}</b>\n"
        f"👥 Проголосовало сейчас: <b>{total_voters}</b>\n"
        f"📨 Пришло по реферальным ссылкам: <b>{total_invited}</b>\n\n"
    )

    if counts:
        text += "📊 <b>Текущий расклад:</b>\n"
        total = sum(counts.values()) or 1
        for i, (oid, cnt) in enumerate(
            sorted(counts.items(), key=lambda x: x[1], reverse=True), 1
        ):
            opt = data["options"].get(oid, {})
            pct = round(cnt / total * 100)
            text += f"{i}. {opt.get('name', oid)} — <b>{cnt}</b> ({pct}%)\n"

    buttons = [
        [InlineKeyboardButton("📊 Полная статистика по раундам", callback_data="admin_stats")],
        [InlineKeyboardButton("📨 Кто кого пригласил",          callback_data="admin_invites")],
        [InlineKeyboardButton("⏭ Следующий раунд вручную",      callback_data="admin_next_round")],
        [InlineKeyboardButton("🏆 Показать победителя",          callback_data="admin_show_result")],
        [InlineKeyboardButton("💡 Свои варианты от участников",  callback_data="admin_customs")],
        [InlineKeyboardButton("🗑 Убрать вариант из раунда",     callback_data="admin_remove")],
    ]

    if update.message:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))
    elif update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))


async def handle_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(update):
        await query.answer("❌ Нет доступа!", show_alert=True)
        return

    data = load_data()
    action = query.data
    back = InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="admin_back")]])

    if action == "admin_stats":
        text = "📊 <b>Статистика по раундам</b>\n\n"
        for r in (1, 2, 3):
            r_votes = data["votes"].get(str(r), {})
            total = len(r_votes)
            info = ROUNDS[r]
            text += (
                f"<b>Раунд {r}</b> "
                f"({info['start'].strftime('%d.%m')}–{info['end'].strftime('%d.%m')})"
                f" — {total} голосов\n"
            )
            if total:
                cnts: dict = {}
                for _, oid in r_votes.items():
                    cnts[oid] = cnts.get(oid, 0) + 1
                for oid, cnt in sorted(cnts.items(), key=lambda x: x[1], reverse=True):
                    opt = data["options"].get(oid, {})
                    text += f"   • {opt.get('name', oid)}: {cnt}\n"
            text += "\n"
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=back)

    elif action == "admin_invites":
        invite_counts = data.get("invite_counts", {})
        invited_by = data.get("invited_by", {})
        if not invite_counts:
            text = "📨 <b>Приглашений пока нет.</b>"
        else:
            text = "📨 <b>Топ пригласивших:</b>\n\n"
            for uid, cnt in sorted(invite_counts.items(), key=lambda x: x[1], reverse=True):
                text += f"• ID <code>{uid}</code> — пригласил <b>{cnt}</b> чел.\n"
            text += f"\n👥 Всего пришли по реферальным ссылкам: <b>{len(invited_by)}</b>"
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=back)

    elif action == "admin_next_round":
        current = data["round"]
        if current >= 3:
            await query.answer("Все раунды уже прошли!", show_alert=True)
            return
        keep = ROUNDS[current]["keep"]
        top_ids = get_top_n(data, current, keep)
        data["active_options"] = top_ids
        data["round"] = current + 1
        save_data(data)
        await query.answer(f"✅ Раунд {current + 1} запущен! Вариантов: {len(top_ids)}.", show_alert=True)
        await show_admin_menu(update, context)

    elif action == "admin_show_result":
        winner_ids = get_top_n(data, data["round"], 1)
        if winner_ids:
            w = data["options"].get(winner_ids[0], {})
            text = f"🏆 <b>Текущий лидер:</b>\n\n🥇 {w.get('name', '???')}\n"
            if w.get("url"):
                text += f"🔗 {w['url']}\n"
        else:
            text = "Данных пока нет."
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=back)

    elif action == "admin_customs":
        customs = data.get("custom_suggestions", [])
        if not customs:
            text = "💡 <b>Своих вариантов ещё нет.</b>"
        else:
            text = "💡 <b>Предложенные участниками варианты:</b>\n\n"
            for c in customs:
                text += f"• {c['name']} — @{c.get('suggested_by', '?')}\n"
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=back)

    elif action == "admin_remove":
        btns = [
            [InlineKeyboardButton(
                f"❌ {data['options'].get(oid, {}).get('name', oid)}",
                callback_data=f"admin_rm_{oid}"
            )]
            for oid in data["active_options"]
        ]
        btns.append([InlineKeyboardButton("◀️ Назад", callback_data="admin_back")])
        await query.edit_message_text("Какой вариант убрать?", reply_markup=InlineKeyboardMarkup(btns))

    elif action.startswith("admin_rm_"):
        opt_id = action.replace("admin_rm_", "")
        if opt_id in data["active_options"]:
            data["active_options"].remove(opt_id)
            save_data(data)
            opt_name = data["options"].get(opt_id, {}).get("name", opt_id)
            await query.answer(f"Убран: {opt_name}", show_alert=True)
        await show_admin_menu(update, context)

    elif action == "admin_back":
        await show_admin_menu(update, context)


# ══════════════════════════════════════════════
#  АВТОЗАДАЧИ
# ══════════════════════════════════════════════

async def auto_advance_rounds(context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    today = date.today()
    for r, info in ROUNDS.items():
        if today == info["end"] + datetime.timedelta(days=1) and data["round"] == r:
            keep = info["keep"]
            top_ids = get_top_n(data, r, keep)
            data["active_options"] = top_ids
            if r + 1 <= 3:
                data["round"] = r + 1
            save_data(data)
            logger.info(f"Автопереход: Раунд {r} → {r+1}, осталось {len(top_ids)} вариантов")


async def send_final_result(context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    if data.get("result_sent") or date.today() < RESULT_DATE:
        return
    winner_ids = get_top_n(data, data["round"], 1)
    if not winner_ids:
        return
    w = data["options"].get(winner_ids[0], {})
    try:
        chat = await context.bot.get_chat(f"@{ADMIN_USERNAME}")
        text = (
            f"🎂🏆 <b>Голосование завершено, Артём!</b>\n\n"
            f"Друзья выбрали:\n\n"
            f"🥇 <b>{w.get('name', '???')}</b>\n"
        )
        if w.get("url"):
            text += f"🔗 {w['url']}\n"
        text += "\n🎉 С днём рождения! 4 апреля 2026!"
        await context.bot.send_message(chat.id, text, parse_mode="HTML")
        data["result_sent"] = True
        save_data(data)
        logger.info("Результат отправлен @Lilux12")
    except Exception as e:
        logger.error(f"Ошибка отправки результата: {e}")


# ══════════════════════════════════════════════
#  ЗАПУСК
# ══════════════════════════════════════════════

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("vote",  cmd_vote))
    app.add_handler(CommandHandler("admin", cmd_admin))

    app.add_handler(CallbackQueryHandler(handle_vote,           pattern="^vote_"))
    app.add_handler(CallbackQueryHandler(handle_share_bot,      pattern="^share_bot$"))
    app.add_handler(CallbackQueryHandler(handle_back_to_vote,   pattern="^back_to_vote$"))
    app.add_handler(CallbackQueryHandler(handle_suggest_custom, pattern="^suggest_custom$"))
    app.add_handler(CallbackQueryHandler(handle_admin_callback, pattern="^admin_"))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    jq = app.job_queue
    jq.run_daily(auto_advance_rounds, time=datetime.time(0, 1, 0))
    jq.run_daily(send_final_result,   time=datetime.time(12, 0, 0))

    logger.info("🤖 Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
