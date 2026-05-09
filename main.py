import telebot
import sqlite3
import json
from telebot import types
import os
import time

BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_IDS_RAW = os.getenv('ADMIN_IDS')

if not BOT_TOKEN:
    try:
        with open('config.json', 'r', encoding='utf-8') as file:
            config = json.load(file)
            BOT_TOKEN = config['bot_token']
            ADMIN_IDS = config['configit _ids']
    except FileNotFoundError:
        print("❌ Ошибка: Файл config.json не найден и переменные не заданы!")
        exit(1)
else:
    try:
        ADMIN_IDS = json.loads(ADMIN_IDS_RAW)
    except:
        ADMIN_IDS = [int(ADMIN_IDS_RAW)]

DATABASE_PATH = '/app/data/event.db'
bot = telebot.TeleBot(BOT_TOKEN)
user_data = {}
topics = ["поиск жилья", "финансы", "медицина", "поиск работы", "легализация"]

event_info = (
    "<b>Uniora | Экспертный день</b>\n"
    "📅 16 мая 2025\n"
    "📍 Szturmowa 1/3, 02-678 Warszawa\n"
    "🕐 16:00\n\n"
    "Один день — несколько профессиональных треков. Эксперты поделятся опытом."
)

def is_user_registered(user_id):
    conn = sqlite3.connect(DATABASE_PATH)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
    exists = cur.fetchone()
    conn.close()
    return exists is not None

def init_db():
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS users
                       (
                           id INTEGER PRIMARY KEY AUTOINCREMENT,
                           user_id INTEGER,
                           name TEXT,
                           phone TEXT,
                           business TEXT,
                           region TEXT,
                           source TEXT
                       )''')
    conn.commit()
    conn.close()

init_db()

def is_admin(chat_id):
    return chat_id in ADMIN_IDS

def get_main_menu_inline():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🎉 О мероприятии", callback_data="main_about"),
        types.InlineKeyboardButton("📝 Зарегистрироваться", callback_data="main_register")
    )
    return markup

def get_cancel_inline():
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ Отменить регистрацию", callback_data="reg_cancel"))
    return markup

def get_reg_confirm_markup():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("✅ Подтвердить", callback_data="reg_finish"),
        types.InlineKeyboardButton("✏️ Изменить данные", callback_data="reg_restart"),
        types.InlineKeyboardButton("❌ Отменить регистрацию", callback_data="reg_cancel")
    )
    return markup

def handle_reg_cancel(chat_id, message_id):
    bot.clear_step_handler_by_chat_id(chat_id)
    user_data.pop(chat_id, None)
    try:
        bot.edit_message_text("❌ Регистрация отменена. Возвращаю в главное меню.", chat_id, message_id)
    except:
        bot.send_message(chat_id, "❌ Регистрация отменена.")

    class FakeMsg:
        def __init__(self, cid):
            self.chat = type('obj', (object,), {'id': cid})
            self.text = "/start"
    send_welcome(FakeMsg(chat_id))

def process_name(message):
    chat_id = message.chat.id
    if message.text == "/cancel": return handle_reg_cancel(chat_id, message.message_id)
    user_data[chat_id] = user_data.get(chat_id, {'source': 'organic'})
    user_data[chat_id]['name'] = message.text

    contact_markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    contact_markup.add(types.KeyboardButton("📱 Отправить номер телефона", request_contact=True))
    msg = bot.send_message(chat_id, "Напишите номер телефона или воспользуйтесь кнопкой:", reply_markup=contact_markup)
    bot.register_next_step_handler(msg, process_phone)

def process_phone(message):
    chat_id = message.chat.id
    user_data[chat_id]['phone'] = message.contact.phone_number if message.contact else message.text
    bot.send_message(chat_id, "Принято ✅", reply_markup=types.ReplyKeyboardRemove())
    msg = bot.send_message(chat_id, "Где ты учишься или работаешь?")
    bot.register_next_step_handler(msg, process_business)

def process_business(message):
    chat_id = message.chat.id
    user_data[chat_id]['business'] = message.text
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for t in topics: markup.add(t)
    bot.send_message(chat_id, "Какая область тебе ближе?", reply_markup=markup)
    msg = bot.send_message(chat_id, "Выберите вариант:")
    bot.register_next_step_handler(msg, process_region)

def process_region(message):
    chat_id = message.chat.id
    if message.text not in topics:
        bot.reply_to(message, "Используйте кнопки!")
        return bot.register_next_step_handler(message, process_region)
    user_data[chat_id]['region'] = message.text
    d = user_data[chat_id]
    confirm_info = (f"📋 <b>Проверьте данные:</b>\n👤 {d['name']}\n📞 {d['phone']}\n🏢 {d['business']}\n🎯 {d['region']}")
    bot.send_message(chat_id, "Данные зафиксированы.", reply_markup=types.ReplyKeyboardRemove())
    bot.send_message(chat_id, confirm_info, parse_mode="HTML", reply_markup=get_reg_confirm_markup())

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    chat_id = call.message.chat.id
    mid = call.message.message_id

    if call.data == "main_about":
        bot.send_message(chat_id, event_info, parse_mode="HTML")
        bot.answer_callback_query(call.id)

    elif call.data == "main_register":
        if is_user_registered(chat_id):
            bot.answer_callback_query(call.id, "Вы уже зарегистрированы!", show_alert=True)
            return
        bot.send_message(chat_id, "Начинаем регистрацию...", reply_markup=types.ReplyKeyboardRemove())
        msg = bot.send_message(chat_id, "Введите ваше Имя и Фамилию:")
        bot.register_next_step_handler(msg, process_name)
        bot.answer_callback_query(call.id)

    elif call.data == "reg_finish":
        d = user_data.get(chat_id)
        if d:
            conn = sqlite3.connect(DATABASE_PATH)
            cur = conn.cursor()
            cur.execute("INSERT INTO users (user_id, name, phone, business, region, source) VALUES (?,?,?,?,?,?)",
                        (chat_id, d['name'], d['phone'], d['business'], d['region'], d['source']))
            conn.commit()
            conn.close()
            bot.edit_message_text("🎉 Вы зарегистрированы! До встречи!", chat_id, mid)
            user_data.pop(chat_id, None)
            bot.send_message(chat_id, "Главное меню:", reply_markup=get_main_menu_inline())
        bot.answer_callback_query(call.id)

    elif call.data == "reg_restart":
        bot.delete_message(chat_id, mid)
        msg = bot.send_message(chat_id, "Введите Имя и Фамилию:")
        bot.register_next_step_handler(msg, process_name)
        bot.answer_callback_query(call.id)

    elif call.data == "reg_cancel":
        handle_reg_cancel(chat_id, mid)
        bot.answer_callback_query(call.id)

    elif call.data == "admin_view_users":
        if not is_admin(chat_id): return
        conn = sqlite3.connect(DATABASE_PATH)
        cur = conn.cursor()
        cur.execute("SELECT name, phone, business, region FROM users")
        rows = cur.fetchall()
        conn.close()

        if not rows:
            bot.send_message(chat_id, "📭 В базе пока нет участников.")
        else:
            res = "<b>👥 Список участников:</b>\n\n"
            for i, u in enumerate(rows, 1):
                res += f"{i}. <b>{u[0]}</b> ({u[1]})\n🏢 {u[2]} | 🎯 {u[3]}\n\n"
            bot.send_message(chat_id, res, parse_mode="HTML")
        bot.answer_callback_query(call.id)

    elif call.data == "admin_stats":
        if not is_admin(chat_id): return
        conn = sqlite3.connect(DATABASE_PATH)
        cur = conn.cursor()
        cur.execute("SELECT region, source FROM users")
        rows = cur.fetchall()
        conn.close()
        if not rows:
            bot.send_message(chat_id, "Статистика пуста.")
        else:
            total = len(rows)
            stats_reg = {k: 0 for k in topics}
            stats_src = {}
            for r, s in rows:
                stats_reg[r] = stats_reg.get(r, 0) + 1
                stats_src[s] = stats_src.get(s, 0) + 1
            res = f"<b>Статистика</b>\n\nВсего регистраций: {total}\n\n"
            res += "<b>По темам:</b>\n"
            for k, v in stats_reg.items():
                res += f"- {k}: {v} ({v / total * 100:.0f}%)\n"
            res += "\n<b>По источникам:</b>\n"
            for k, v in stats_src.items():
                res += f"- {k}: {v} ({v / total * 100:.0f}%)\n"
            bot.send_message(chat_id, res, parse_mode="HTML")
        bot.answer_callback_query(call.id)

    elif call.data == "admin_broadcast_start":
        if not is_admin(chat_id): return
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ Отмена", callback_data="stop_broadcast"))
        bot.send_message(chat_id, "Введите текст рассылки:", reply_markup=markup)
        bot.register_next_step_handler(call.message, process_broadcast)
        bot.answer_callback_query(call.id)

    elif call.data == "stop_broadcast":
        bot.clear_step_handler_by_chat_id(chat_id)
        bot.answer_callback_query(call.id, "Рассылка отменена")
        welcome_admin(call.message)

    elif call.data == "admin_exit":
        bot.delete_message(chat_id, mid)
        class FakeMsg:
            def __init__(self, cid): self.chat = type('obj', (object,), {'id': cid}); self.text = "/start"
        send_welcome(FakeMsg(chat_id))
        bot.answer_callback_query(call.id)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    text = message.text if hasattr(message, 'text') and message.text else "/start"
    parts = text.split()
    source = parts[1] if len(parts) > 1 else "telegram"
    user_data[chat_id] = {'source': source}

    bot.send_message(chat_id, "Добро пожаловать! Выберите действие:", reply_markup=get_main_menu_inline())

@bot.message_handler(commands=['admin'])
def welcome_admin(message):
    if not is_admin(message.chat.id):
        bot.send_message(message.chat.id, "❌ У вас нет прав доступа.")
        return

    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("👥 Посмотреть участников", callback_data="admin_view_users"),
        types.InlineKeyboardButton("📢 Рассылка участникам", callback_data="admin_broadcast_start"),
        types.InlineKeyboardButton("📊 Просмотр статистики", callback_data="admin_stats"),
        types.InlineKeyboardButton("🚪 Выйти", callback_data="admin_exit")
    )

    bot.send_message(message.chat.id, "🛠 <b>Панель администратора</b>", parse_mode="HTML", reply_markup=markup)

def process_broadcast(message):
    if not is_admin(message.chat.id): return
    conn = sqlite3.connect(DATABASE_PATH)
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users")
    users = cur.fetchall()
    conn.close()
    count = 0
    for u in users:
        try:
            bot.send_message(u[0], message.text)
            count += 1
        except: pass
    bot.send_message(message.chat.id, f"✅ Рассылка завершена. Отправлено: {count} чел.")
    welcome_admin(message)

@bot.message_handler(commands=['get_db'])
def get_db_file(message):
    if is_admin(message.chat.id):
        try:
            with open(DATABASE_PATH, 'rb') as f:
                bot.send_document(message.chat.id, f)
        except Exception as e:
            bot.send_message(message.chat.id, f"Ошибка: {e}")

@bot.message_handler(content_types=['document'])
def handle_db_restore(message):
    if not is_admin(message.chat.id):
        return

    if message.document.file_name == 'event.db':
        try:
            file_info = bot.get_file(message.document.file_id)
            downloaded_file = bot.download_file(file_info.file_path)

            with open(DATABASE_PATH, 'wb') as new_db:
                new_db.write(downloaded_file)

            bot.reply_to(message, "✅ База данных успешно восстановлена!")
        except Exception as e:
            bot.reply_to(message, f"❌ Ошибка при восстановлении: {e}")
    else:
        bot.reply_to(message, "⚠️ Файл должен называться 'event.db'")


#test commit
if __name__ == '__main__':
    import time

    print("Бот запущен...")
    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=60)
        except Exception as e:
            print(f"Ошибка сети: {e}")
            time.sleep(5)
            print("🔄 Попытка перезапуска бота...")