import schedule
import time
import io
import telebot
import sqlite3
from telebot import types
import datetime
import threading
from bs4 import BeautifulSoup
from parsing_schedule import get_schedule_html, generate_schedule_text
from config import TOKEN, group_urls, ADMIN_ID

start_time = time.time()

conn = sqlite3.connect('database.db', check_same_thread=False)
cursor = conn.cursor()
lock = threading.Lock()

cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        last_name TEXT,
        group_name TEXT,
        registration_date TEXT,
        settings_classroom INTEGER DEFAULT 1,
        settings_teacher INTEGER DEFAULT 1,
        settings_display_days INTEGER DEFAULT 7,
        send_schedule INTEGER DEFAULT 1
    )
''')
conn.commit()

bot = telebot.TeleBot(TOKEN)


@bot.message_handler(
    func=lambda message: message.text in {"🔧 Админ-панель", "↩️ В админ-панель"} and message.from_user.id in [
        ADMIN_ID])
def admin_panel(message):
    user_id = message.from_user.id

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(types.KeyboardButton("📤 Рассылка"))
    markup.row(types.KeyboardButton("📥 Получить статистику"))
    markup.row(types.KeyboardButton("📊 Выслать базу данных"))
    markup.row(types.KeyboardButton("↩️ В меню"))

    bot.send_message(user_id, "Добро пожаловать в админ-панель!", reply_markup=markup)


@bot.message_handler(func=lambda message: message.text == "📊 Выслать базу данных")
def send_database(message):
    user_id = message.from_user.id

    if user_id not in [ADMIN_ID]:
        bot.send_message(user_id, "У вас нет доступа к этой команде.")
        return

    with lock:
        cursor.execute('SELECT * FROM users')
        all_users = cursor.fetchall()

    database_text = "ID пользователя | Имя пользователя | Имя | Фамилия | Группа | Дата регистрации | " \
                    "Кабинеты | Учителя | Дни | Рассылка\n"

    for user_data in all_users:
        user_id, username, first_name, last_name, group_name, registration_date, \
            settings_classroom, settings_teacher, settings_display_days, send_schedule = user_data

        database_text += (
            f"{user_id} | {username} | {first_name} | {last_name} | {group_name} | {registration_date} | "
            f"{settings_classroom} | {settings_teacher} | {settings_display_days} | {send_schedule}\n"
        )

    with io.StringIO(database_text) as f:
        f.name = "user_database.txt"
        bot.send_document(user_id, f)

    bot.send_message(user_id, "База данных отправлена в виде .txt файла.")


@bot.message_handler(func=lambda message: message.text == "📤 Рассылка")
def send_broadcast(message):
    user_id = message.from_user.id

    if user_id not in {ADMIN_ID}:
        bot.send_message(user_id, "У вас нет доступа к этой команде.")
        return

    bot.send_message(user_id, "Введите сообщение для рассылки (/cancel для отмены):")

    bot.register_next_step_handler(message, process_broadcast)


def process_broadcast(message):
    broadcast_message = message.text

    if broadcast_message == "/cancel":
        return

    with lock:
        cursor.execute('SELECT user_id FROM users')
        all_users = cursor.fetchall()

    for user_data in all_users:
        user_id = user_data[0]

        try:
            bot.send_message(user_id, broadcast_message)
        except Exception as e:
            print(f"Error sending broadcast to user {user_id}: {e}")
            remove_user_from_db(user_id, cursor, conn)


def remove_user_from_db(user_id, cursor, conn):
    cursor.execute("DELETE FROM users WHERE user_id=?", (user_id,))
    conn.commit()
    print(f"User {user_id} removed from the database.")


@bot.message_handler(func=lambda message: message.text == "📥 Получить статистику")
def get_statistics(message):
    user_id = message.from_user.id

    if user_id not in [ADMIN_ID]:
        bot.send_message(user_id, "У вас нет доступа к этой команде.")
        return

    with lock:
        cursor.execute('SELECT COUNT(user_id) FROM users')
        user_count = cursor.fetchone()[0]

    current_time = time.time()
    uptime_seconds = current_time - start_time
    uptime_str = str(datetime.timedelta(seconds=int(uptime_seconds)))

    statistics_text = (
        f"👥 Количество пользователей: {user_count}\n"
        f"⏳ Время работы бота: {uptime_str}"
    )

    bot.send_message(user_id, statistics_text)


def send_navigation_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)

    markup.row(types.KeyboardButton("🗓 Расписание"), types.KeyboardButton("🔄 Сменить группу"))
    markup.row(types.KeyboardButton("⚙ Настройки"), types.KeyboardButton("ℹ️ Информация"))

    if user_id in [ADMIN_ID]:
        markup.row(types.KeyboardButton("🔧 Админ-панель"))

    bot.send_message(user_id, "Меню навигации", reply_markup=markup)


@bot.message_handler(commands=['start'])
def handle_start(message):
    user_id = message.from_user.id
    first_name = message.from_user.first_name

    with lock:
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user_data = cursor.fetchone()

    if user_data:
        send_navigation_menu(user_id)
        bot.send_message(user_id, f"Привет, {first_name}! Ты уже зарегистрирован.")
    else:
        keyboard = types.InlineKeyboardMarkup()

        for group, url in group_urls.items():
            button = types.InlineKeyboardButton(text=group, callback_data=group)
            keyboard.add(button)

        bot.send_message(user_id, "Привет! Выбери свою группу из списка ниже для продолжения:", reply_markup=keyboard)


@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    user_id = call.from_user.id
    username = call.from_user.username
    first_name = call.from_user.first_name
    last_name = call.from_user.last_name

    group_name = call.data

    with lock:
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user_data = cursor.fetchone()

    if user_data:
        with lock:
            cursor.execute('''
                UPDATE users
                SET group_name = ?
                WHERE user_id = ?
            ''', (group_name, user_id))
            conn.commit()

        bot.send_message(user_id, f"Привет, {first_name}! Ты успешно сменил группу на {group_name}.")
        send_navigation_menu(user_id)
    else:
        registration_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with lock:
            cursor.execute('''
                INSERT INTO users (user_id, username, first_name, last_name, group_name, registration_date)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, username, first_name, last_name, group_name, registration_date))

            cursor.execute('''
                UPDATE users
                SET settings_classroom = 1, settings_teacher = 1
                WHERE user_id = ?
            ''', (user_id,))
            conn.commit()

        send_navigation_menu(user_id)

        bot.send_message(user_id, f"Привет, {first_name}! Ты успешно зарегистрирован. Группа: {group_name}")


@bot.message_handler(func=lambda message: message.text == "🗓 Расписание")
def view_schedule(message):
    user_id = message.from_user.id

    with lock:
        cursor.execute(
            'SELECT group_name, settings_teacher, settings_classroom, settings_display_days FROM users WHERE user_id = ?',
            (user_id,))
        user_data = cursor.fetchone()

    if not user_data:
        bot.send_message(user_id, "Вы не выбрали группу. Пожалуйста, выберите группу через команду /start.")
        return

    group_name, settings_teacher, settings_classroom, settings_display_days = user_data

    user_settings = {
        'settings_teacher': settings_teacher,
        'settings_classroom': settings_classroom,
        'settings_display_days': settings_display_days
    }

    url = group_urls.get(group_name)

    if not url:
        bot.send_message(user_id, f"URL для группы {group_name} не найден.")
        return

    schedule_html = get_schedule_html(url)

    if not schedule_html:
        bot.send_message(user_id, "Ошибка при получении расписания.")
        return

    soup = BeautifulSoup(schedule_html, 'html.parser')
    schedule_rows = soup.find_all('tr')
    schedule_text = generate_schedule_text(schedule_rows, user_settings)

    bot.send_message(user_id, schedule_text)


@bot.message_handler(func=lambda message: message.text == "🔄 Сменить группу")
def change_group(message):
    user_id = message.from_user.id

    with lock:
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user_data = cursor.fetchone()

    if user_data:
        keyboard = types.InlineKeyboardMarkup()

        for group, url in group_urls.items():
            button = types.InlineKeyboardButton(text=group, callback_data=f'{group}')
            keyboard.add(button)

        bot.send_message(user_id, "Выберите новую группу:", reply_markup=keyboard)
    else:
        bot.send_message(user_id, "Вы не зарегистрированы. Выберите группу через команду /start.")


@bot.message_handler(func=lambda message: message.text == "⚙ Настройки")
def settings_menu(message):
    user_id = message.from_user.id

    with lock:
        cursor.execute(
            'SELECT settings_classroom, settings_teacher, settings_display_days, send_schedule FROM users WHERE user_id = ?',
            (user_id,))
        user_settings = cursor.fetchone()

    if not user_settings:
        bot.send_message(user_id, "Вы не зарегистрированы. Пожалуйста, выберите группу через команду /start.")
        return

    classroom_status = 'Включено' if user_settings[0] == 1 else 'Отключено'
    teacher_status = 'Включено' if user_settings[1] == 1 else 'Отключено'
    schedule_days = 'Включено' if user_settings[3] == 1 else 'Отключено'
    max_days = user_settings[2]

    settings_text = (
        f"Текущие настройки:\n"
        f"👩‍🏫 Учителя в расписании: {teacher_status}\n"
        f"🏫 Кабинеты в расписании: {classroom_status}\n"
        f"📅 Количество дней в расписании: {max_days}\n"
        f"📆 Отправлять рассылку расписания: {schedule_days}\n\n"
        f"Выберите параметр, который хотите изменить:"
    )

    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row(types.KeyboardButton("👩‍🏫 Учителя"), types.KeyboardButton("🏫 Кабинеты"))
    keyboard.row(types.KeyboardButton("📅 Изменить количество дней"), types.KeyboardButton("📆 Рассылка расписания"))
    keyboard.row(types.KeyboardButton("↩️ В меню"))

    bot.send_message(user_id, settings_text, reply_markup=keyboard)


@bot.message_handler(func=lambda message: message.text in {"👩‍🏫 Учителя", "🏫 Кабинеты", "📅 Изменить количество дней",
                                                           "📆 Рассылка расписания"})
def change_settings(message):
    user_id = message.from_user.id
    selected_setting = message.text

    if selected_setting == "👩‍🏫 Учителя":
        update_toggle_setting(user_id, "settings_teacher", "👩‍🏫 Учителя")
    elif selected_setting == "🏫 Кабинеты":
        update_toggle_setting(user_id, "settings_classroom", "🏫 Кабинеты")
    elif selected_setting == "📅 Изменить количество дней":
        send_days_count_menu(user_id)
    elif selected_setting == "📆 Рассылка расписания":
        update_toggle_setting(user_id, "send_schedule", "📆 Рассылка расписания")
    else:
        return


def update_toggle_setting(user_id, setting_key, setting_name):
    with lock:
        cursor.execute(f'SELECT {setting_key} FROM users WHERE user_id = ?', (user_id,))
        current_setting_value = cursor.fetchone()[0]

    new_setting_value = 1 if current_setting_value == 0 else 0

    with lock:
        cursor.execute(f'UPDATE users SET {setting_key} = ? WHERE user_id = ?', (new_setting_value, user_id))
        conn.commit()

    bot.send_message(user_id, f"Настройка '{setting_name}' успешно изменена!")


def send_days_count_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)

    for days_count in [1, 3, 7, 14]:
        markup.add(types.KeyboardButton(str(days_count)))
    markup.add(types.KeyboardButton("↩️ В меню"))

    bot.send_message(user_id, "Выберите количество дней для отображения в расписании:", reply_markup=markup)


@bot.message_handler(func=lambda message: message.text.isdigit() and int(message.text) in [1, 3, 7, 14])
def handle_days_count_selection(message):
    user_id = message.from_user.id
    days_count = int(message.text)

    with lock:
        cursor.execute('UPDATE users SET settings_display_days = ? WHERE user_id = ?', (days_count, user_id))
        conn.commit()

    bot.send_message(user_id, f"Количество дней для отображения в расписании успешно изменено на {days_count}.")
    send_navigation_menu(user_id)


@bot.message_handler(func=lambda message: message.text == "ℹ️ Информация")
def about(message):
    user_id = message.from_user.id

    about_text = (
        f"ℹ️ Важная информация о боте:\n\n"
        f"Рассылка расписания проводится в 6:00 и 18:00.\n"
        f"Бот находится в бета-тестировании, сейчас доступна для использования только первая подгруппа.\n"
        f"Если вы хотите сообщить баг или предложить свою идею, то свяжитесь с создателем через меню."
    )

    bot.send_message(user_id, about_text)


@bot.message_handler(func=lambda message: message.text in {"↩️ В меню"})
def back_to_menu(message):
    user_id = message.from_user.id
    send_navigation_menu(user_id)


def send_schedule_to_all_users():
    with lock:
        cursor.execute(
            'SELECT user_id, group_name, settings_teacher, settings_classroom, settings_display_days, send_schedule FROM users')
        all_users = cursor.fetchall()

    for user_data in all_users:
        user_id, group_name, settings_teacher, settings_classroom, settings_display_days, send_schedule = user_data

        if send_schedule == 1:
            user_settings = {
                'settings_teacher': settings_teacher,
                'settings_classroom': settings_classroom,
                'settings_display_days': settings_display_days
            }

            url = group_urls.get(group_name)

            if url:
                schedule_html = get_schedule_html(url)

                if schedule_html:
                    soup = BeautifulSoup(schedule_html, 'html.parser')
                    schedule_rows = soup.find_all('tr')
                    schedule_text = generate_schedule_text(schedule_rows, user_settings)

                    try:
                        bot.send_message(user_id, schedule_text)
                    except Exception as e:
                        print(f"Error sending broadcast to user {user_id}: {e}")
                        remove_user_from_db(user_id, cursor, conn)

                    time.sleep(0.1)


schedule.every().day.at("06:00").do(send_schedule_to_all_users)
schedule.every().day.at("18:00").do(send_schedule_to_all_users)


def scheduled_job():
    while True:
        schedule.run_pending()
        time.sleep(1)


def bot_polling_and_schedule():
    threading.Thread(target=scheduled_job).start()

    while True:
        try:
            bot.polling(none_stop=True, timeout=90)
        except Exception as e:
            print(datetime.datetime.now(), e)
            time.sleep(5)
            continue


if __name__ == "__main__":
    bot_polling_and_schedule()
