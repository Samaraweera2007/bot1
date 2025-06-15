import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters, CallbackQueryHandler
)
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
import asyncio
import json
import os
from telegram.error import TelegramError


TOKEN = os.getenv("7586032938:AAEUn_sCvmw4lXrodnDt8RITjiCFf5XhSiA") # BotFather එකෙන් ගත් token එක මෙතැන දාන්න
REMINDER_FILE = "reminders.json"
CHANNEL_FILE = "channels.json"

user_states = {}      # user_id: {"step": str, "subject": str, "time": str}
user_schedules = {}   # user_id: [(subject, time_str, repeat)]
user_channels = {}    # user_id: channel_id

scheduler = BackgroundScheduler()
scheduler.start()

logging.basicConfig(level=logging.INFO)

def save_reminders():
    with open(REMINDER_FILE, "w", encoding="utf-8") as f:
        json.dump(user_schedules, f)

def load_reminders():
    global user_schedules
    if os.path.exists(REMINDER_FILE):
        with open(REMINDER_FILE, "r", encoding="utf-8") as f:
            user_schedules = json.load(f)
            user_schedules = {int(k): v for k, v in user_schedules.items()}

def save_channels():
    with open(CHANNEL_FILE, "w", encoding="utf-8") as f:
        json.dump(user_channels, f)

def load_channels():
    global user_channels
    if os.path.exists(CHANNEL_FILE):
        with open(CHANNEL_FILE, "r", encoding="utf-8") as f:
            user_channels = json.load(f)
            user_channels = {int(k): v for k, v in user_channels.items()}

def reschedule_all_reminders(app):
    scheduler.remove_all_jobs()
    for user_id, reminders in user_schedules.items():
        for r in reminders:
            subject, time_str, repeat = r[:3]
            hour, minute = map(int, time_str.split(":"))
            # Add your job scheduling logic here, e.g.:
            scheduler.add_job(
                lambda uid=user_id, sub=subject: send_reminder(app, uid, sub),
                'cron',
                hour=hour,
                minute=minute,
                id=f"{user_id}_{subject}"
            )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *A/L Reminder Bot* එකට _සාදරයෙන් පිළිගනිමු!_\n\n"
        "🛠️ *Commands:*\n"
        "➕ /add - නව reminder එකක් එකතු කරන්න\n"
        "📋 /list - ඔබගේ reminders බලන්න\n"
        "🗑️ /delete - අංකය reply කර reminder එකක් ඉවත් කරන්න\n\n"
        "🔄 Reminders set කිරීමේදී, bot එකේ උපදෙස් අනුව පිළිතුරු දෙන්න.\n"
        "🕒 Reminders වෙනස්/ඉවත් කිරීමට, /list command එකෙන් අංකය භාවිතා කරන්න.\n\n"
        "❓ උදව් අවශ්‍ය නම්, මෙම commands භාවිතා කරන්න!",
        parse_mode="Markdown"
    )

async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_states[user_id] = {"step": "subject"}
    await update.message.reply_text("පාඩමේ නම කියන්න (උදා: ganithaya):")

from telegram import InlineKeyboardMarkup, InlineKeyboardButton

# 1. List command
async def list_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    reminders = user_schedules.get(user_id, [])
    if not reminders:
        await update.message.reply_text("ඔයාට set කරපු reminders නැහැ.")
        return

    msg = "📋 *Reminders List:*\n\n"
    for i, r in enumerate(reminders, 1):
        subject = r[0]
        time_str = r[1]
        repeat = r[2]
        msg += (
            f"*{i}.* `{subject}`\n"
            f"   • Time: ⏰ `{time_str}`\n"
            f"   • Repeat: 🔁 `{repeat}`\n\n"
        )
    await update.message.reply_text(msg, parse_mode="Markdown")

# --- Combine number_reply_handler and handle_message ---
async def main_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    state = user_states.get(user_id)

    # Number reply එකට විස්තර + buttons
    if not state and text.isdigit():
        reminders = user_schedules.get(user_id, [])
        idx = int(text) - 1
        if idx < 0 or idx >= len(reminders):
            await update.message.reply_text("අංකය වැරදියි.")
            return
        r = reminders[idx]
        subject = r[0]
        time_str = r[1]
        repeat = r[2]
        msg = (
            f"🔔 *Reminder විස්තරය:*\n"
            f"*Subject:* `{subject}`\n"
            f"*Time:* ⏰ `{time_str}`\n"
            f"*Repeat:* 🔁 `{repeat}`"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🕒 Change Time", callback_data=f"changetime_{idx}"),
            InlineKeyboardButton("✏️ Change Subject", callback_data=f"changesubject_{idx}")],
            [InlineKeyboardButton("🗑️ Delete", callback_data=f"delete_{idx}")],
        ])
        await update.message.reply_text(
            msg,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        return

    # Subject change handle
    if state and state.get("step") == "change_subject":
        idx = state.get("reminder_idx")
        reminders = user_schedules.get(user_id, [])
        if idx is None or not (0 <= idx < len(reminders)):
            await update.message.reply_text("Reminder එක හමු නොවුණා.")
            user_states.pop(user_id, None)
            return
        new_subject = text.strip()
        r = reminders[idx]
        reminders[idx] = (new_subject, r[1], r[2])  # subject, time, repeat
        save_reminders()
        reschedule_all_reminders(context.application)
        await update.message.reply_text(
            "✅ *Subject එක සාර්ථකව update කරා!*",
            parse_mode="Markdown"
        )
        user_states.pop(user_id, None)
        return

    # If user is in reminder_action state, treat as number reply
    if state and state.get("step") == "delete_reminder":
        if not text.isdigit():
            await update.message.reply_text("අංකයක් දෙන්න.")
            return
        idx = int(text) - 1
        reminders = user_schedules.get(user_id, [])
        if 0 <= idx < len(reminders):
            removed = reminders.pop(idx)
            save_reminders()
            await update.message.reply_text(f"'{removed[0]}' reminder එක delete කරා!")
        else:
            await update.message.reply_text("⚠️ _අංකය වැරදියි. කරුණාකර නිවැරදි අංකයක් දෙන්න!_", parse_mode="Markdown")
        user_states.pop(user_id, None)
        return

    # Handle time change
    if state and state.get("step") == "change_time":
        idx = state["reminder_idx"]
        reminders = user_schedules.get(user_id, [])
        if not (0 <= idx < len(reminders)):
            await update.message.reply_text("Reminder එක හමු නොවුණා.")
            user_states.pop(user_id, None)
            return
        try:
            hour, minute = map(int, text.split(":"))
        except ValueError:
            await update.message.reply_text("වෙලාව හරි format එකෙන් දෙන්න (උදා: 18:00)")
            return
        r = reminders[idx]
        reminders[idx] = (r[0], text, r[2])  # subject, new time, repeat
        save_reminders()
        # මෙතැනදී scheduler එක re-schedule කරන්න!
        reschedule_all_reminders(context.application)
        await update.message.reply_text(f"'{r[0]}' reminder එකේ වෙලාව {text} ලෙස සාර්ථකව update කරා! ✅")
        user_states.pop(user_id, None)
        return

    # Change Time state (button එකෙන්)
    if state and state.get("step") == "change_time_new":
        idx = state.get("reminder_idx")
        reminders = user_schedules.get(user_id, [])
        if idx is None or not (0 <= idx < len(reminders)):
            await update.message.reply_text("⚠️ Reminder එක හමු නොවුණා.")
            user_states.pop(user_id, None)
            return
        try:
            hour, minute = map(int, text.split(":"))
        except ValueError:
            await update.message.reply_text("⏰ වෙලාව හරි format එකෙන් දෙන්න (උදා: 18:00)")
            return
        r = reminders[idx]
        reminders[idx] = (r[0], text, r[2])  # subject, new time, repeat
        save_reminders()
        reschedule_all_reminders(context.application)
        await update.message.reply_text("⏰ Time එක සාර්ථකව update කරා! ✅", parse_mode="Markdown")
        user_states.pop(user_id, None)
        return

    if state and state.get("step") == "delete_by_name":
        subject_to_delete = text.strip().lower()
        reminders = user_schedules.get(user_id, [])
        found = False
        for idx, r in enumerate(reminders):
            if r[0].strip().lower() == subject_to_delete:
                removed = reminders.pop(idx)
                save_reminders()
                await update.message.reply_text(f"'{removed[0]}' reminder එක delete කරා!")
                found = True
                break
        if not found:
            await update.message.reply_text("එවැනි reminder එකක් නැහැ.")
        user_states.pop(user_id, None)
        return

    if not state:
        await update.message.reply_text("පාඩමක් set කරන්න /add කියන්න.")
        return

    if state["step"] == "subject":
        user_states[user_id]["subject"] = text
        user_states[user_id]["step"] = "time"
        await update.message.reply_text("වෙලාව කියන්න (උදා: 18:00):")
    elif state["step"] == "time":
        try:
            time_obj = datetime.strptime(text, "%H:%M").time()
            user_states[user_id]["time"] = text
            # Channel id එක save වෙලා නැත්නම් අහන්න
            if user_id not in user_channels:
                user_states[user_id]["step"] = "channel"
                await update.message.reply_text("Channel ID එක type කරන්න (උදා: @yourchannel හෝ -100XXXXXXXXXX):")
            else:
                user_states[user_id]["step"] = "repeat"
                reply_markup = ReplyKeyboardMarkup(
                    [["daily", "weekly", "none"]],
                    one_time_keyboard=True,
                    resize_keyboard=True
                )
                await update.message.reply_text(
                    "Repeat එකක් තෝරන්න:",
                    reply_markup=reply_markup
                )
        except ValueError:
            await update.message.reply_text("වෙලාව හරි format එකෙන් දෙන්න (උදා: 18:00):")
    elif state["step"] == "channel":
        user_channels[user_id] = text
        save_channels()
        user_states[user_id]["step"] = "repeat"
        reply_markup = ReplyKeyboardMarkup(
            [["daily", "weekly", "none"]],
            one_time_keyboard=True,
            resize_keyboard=True
        )
        await update.message.reply_text(
            "Repeat එකක් තෝරන්න:",
            reply_markup=reply_markup
        )
    elif state["step"] == "repeat":
        repeat = text.lower()
        if repeat not in ["daily", "weekly", "none"]:
            await update.message.reply_text("repeat එක daily, weekly, none වලින් එකක් ලෙස තෝරන්න.")
            return

        subject = user_states[user_id]["subject"]
        time_str = user_states[user_id]["time"]
        channel_id = user_channels[user_id]

        if user_id not in user_schedules:
            user_schedules[user_id] = []
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M")
        last_played = "--"
        user_schedules[user_id].append((subject, time_str, repeat, created_at, last_played))
        save_reminders()  # Save to file

        # Reminder function - send to selected channel with buttons
        async def send_reminder():
            await context.bot.send_message(
                chat_id=channel_id,
                text=f"'{subject}' පාඩමට {time_str} ට වෙලාවයි!\n\nStatus එක තෝරන්න:",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("✅ Completed", callback_data="completed"),
                        InlineKeyboardButton("❌ Not Completed", callback_data="not_completed")
                    ]
                ])
            )

        hour, minute = map(int, time_str.split(":"))

        if repeat == "daily":
            scheduler.add_job(
                lambda: asyncio.run(send_reminder()),
                'cron',
                hour=hour,
                minute=minute,
                id=f"{user_id}_{subject}_{time_str}_{channel_id}_daily",
                replace_existing=True
            )
            msg = f"'{subject}' පාඩම {time_str} ට **daily** set කරා!"
        elif repeat == "weekly":
            scheduler.add_job(
                lambda: asyncio.run(send_reminder()),
                'cron',
                day_of_week='mon',  # අවශ්‍ය නම් වෙනස් කරන්න
                hour=hour,
                minute=minute,
                id=f"{user_id}_{subject}_{time_str}_{channel_id}_weekly",
                replace_existing=True
            )
            msg = f"'{subject}' පාඩම {time_str} ට **weekly** set කරා! (සඳුදා)"
        else:
            now = datetime.now()
            reminder_time = datetime.combine(now.date(), datetime.strptime(time_str, "%H:%M").time())
            if reminder_time < now:
                reminder_time += timedelta(days=1)
            scheduler.add_job(
                lambda: asyncio.run(send_reminder()),
                'date',
                run_date=reminder_time
            )
            msg = f"'{subject}' පාඩම {time_str} ට set කරා! (එක් වරක් පමණයි)"

        await update.message.reply_text(msg, reply_markup=ReplyKeyboardRemove())
        user_states.pop(user_id)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data.startswith("changetime_"):
        idx = int(data.split("_")[1])
        reminders = user_schedules.get(user_id, [])
        if 0 <= idx < len(reminders):
            user_states[user_id] = {"step": "change_time_new", "reminder_idx": idx}
            await query.edit_message_text("⏰ අලුත් වෙලාව (උදා: 18:00) reply කරන්න:")
        else:
            await query.edit_message_text("⚠️ අංකය වැරදියි.")
    elif data.startswith("delete_"):
        idx = int(data.split("_")[1])
        reminders = user_schedules.get(user_id, [])
        if 0 <= idx < len(reminders):
            removed = reminders.pop(idx)
            save_reminders()
            reschedule_all_reminders(context.application)
            await query.edit_message_text(f"'{removed[0]}' reminder එක delete කරා!")
        else:
            await query.edit_message_text("අංකය වැරදියි.")
        user_states.pop(user_id, None)

    elif data.startswith("changesubject_"):
        idx = int(data.split("_")[1])
        reminders = user_schedules.get(user_id, [])
        if 0 <= idx < len(reminders):
            user_states[user_id] = {"step": "change_subject", "reminder_idx": idx}
            await query.edit_message_text("අලුත් subject එක reply කරන්න:")
        else:
            await query.edit_message_text("අංකය වැරදියි.")
    elif data == "completed":
        await query.edit_message_text(
            query.message.text + "\n\n✅ Completed!\n\n🎉 සුභ පැතුම්! ඔබට ජය වේවා!"
        )
    elif data == "not_completed":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("ඊළඟ දවසට යළි set කරන්න", callback_data="reschedule")],
            [InlineKeyboardButton("වෙලාව වෙනස් කරන්න", callback_data="change_time")],
            [InlineKeyboardButton("නැහැ, අවශ්‍ය නැහැ (delete)", callback_data="no_reschedule")]
        ])
        await query.edit_message_text(
            query.message.text + "\n\n❌ Not Completed!\n\nඔයාට reminder එකට කරන්න ඕන දේ තෝරන්න:",
            reply_markup=keyboard
        )
    elif data == "change_time":
        # Save state for user to expect new time
        import re
        m = re.search(r"'(.+?)' පාඩමට (\d{2}:\d{2}) ට", query.message.text)
        if m:
            subject = m.group(1)
            time_str = m.group(2)
            user_id = None
            for uid, reminders in user_schedules.items():
                for r in reminders:
                    if len(r) == 3:
                        s, t, _ = r
                    else:
                        s, t, *_ = r
                    if s == subject and t == time_str:
                        user_id = uid
                        break
                if user_id:
                    break
            if user_id:
                user_states[user_id] = {
                    "step": "change_time",
                    "subject": subject,
                    "old_time": time_str
                }
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"'{subject}' reminder එකට නව වෙලාව type කරන්න (උදා: 19:30):"
                )
                await query.edit_message_text(
                    query.message.text + "\n\n🕒 නව වෙලාව user inbox එකට type කරන්න."
                )
            else:
                await query.edit_message_text(
                    query.message.text + "\n\n⚠️ User හඳුනාගන්න බැරි වුණා."
                )
        else:
            await query.edit_message_text(
                query.message.text + "\n\n⚠️ Reminder info හඳුනාගන්න බැරි වුණා."
            )
    elif data == "reschedule":
        import re
        m = re.search(r"'(.+?)' පාඩමට (\d{2}:\d{2}) ට", query.message.text)
        if m:
            subject = m.group(1)
            time_str = m.group(2)
            user_id = None
            channel_id = query.message.chat_id
            for uid, reminders in user_schedules.items():
                for r in reminders:
                    if len(r) == 3:
                        s, t, _ = r
                    else:
                        s, t, *_ = r
                    if s == subject and t == time_str:
                        user_id = uid
                        break
                if user_id:
                    break
            if user_id:
                now = datetime.now()
                reminder_time = datetime.combine(now.date() + timedelta(days=1), datetime.strptime(time_str, "%H:%M").time())
                async def send_reminder():
                    await context.bot.send_message(
                        chat_id=channel_id,
                        text=f"'{subject}' පාඩමට {time_str} ට වෙලාවයි!\n\nStatus එක තෝරන්න:",
                        reply_markup=InlineKeyboardMarkup([
                            [
                                InlineKeyboardButton("✅ Completed", callback_data="completed"),
                                InlineKeyboardButton("❌ Not Completed", callback_data="not_completed")
                            ]
                        ])
                    )
                scheduler.add_job(
                    lambda: asyncio.run(send_reminder()),
                    'date',
                    run_date=reminder_time
                )
                await query.edit_message_text(
                    query.message.text + "\n\n🔄 Reminder එක ඊළඟ දවසට යළි set කරා!"
                )
            else:
                await query.edit_message_text(
                    query.message.text + "\n\n⚠️ Reschedule කරන්න බැරි වුණා."
                )
        else:
            await query.edit_message_text(
                query.message.text + "\n\n⚠️ Reminder info හඳුනාගන්න බැරි වුණා."
            )
    elif data == "no_reschedule":
        # --- Delete reminder from user_schedules ---
        import re
        m = re.search(r"'(.+?)' පාඩමට (\d{2}:\d{2}) ට", query.message.text)
        if m:
            subject = m.group(1)
            time_str = m.group(2)
            user_id = None
            for uid, reminders in user_schedules.items():
                for r in reminders:
                    if len(r) == 3:
                        s, t, _ = r
                    else:
                        s, t, *_ = r
                    if s == subject and t == time_str:
                        user_id = uid
                        break
                if user_id:
                    break
            if user_id:
                # Remove from list
                user_schedules[user_id] = [
                    r for r in user_schedules[user_id]
                    if not (r[0] == subject and r[1] == time_str)
                ]
                # Save to file
                save_reminders()
        await query.edit_message_text(
            query.message.text + "\n\n⛔️ Reminder එක delete කරා. ඔබට සුභ දවසක්!"
        )

async def delete_reminder_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    reminders = user_schedules.get(user_id, [])
    if not reminders:
        await update.message.reply_text("ඔයාට set කරපු reminders නැහැ.")
        return
    msg = "Delete කරන්න reminder එකේ අංකය reply කරන්න:\n"
    for i, r in enumerate(reminders, 1):
        subject, time_str, repeat = r[:3]
        msg += f"{i}. {subject} - {time_str} - {repeat}\n"
    user_states[user_id] = {"step": "delete_reminder"}
    await update.message.reply_text(msg)

async def error_handler(update, context: ContextTypes.DEFAULT_TYPE):
    print(f"Exception while handling an update: {context.error}")

app = ApplicationBuilder().token(TOKEN).build()
load_reminders()
load_channels()
reschedule_all_reminders(app)

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("add", add_command))
app.add_handler(CommandHandler("list", list_reminders))
app.add_handler(CommandHandler("delete", delete_reminder_command))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, main_message_handler))
app.add_handler(CallbackQueryHandler(button_handler))
app.add_error_handler(error_handler)

app.run_polling()
