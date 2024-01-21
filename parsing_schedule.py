import requests

def get_schedule_html(url):
    response = requests.get(url)
    response.encoding = 'windows-1251'

    if response.status_code == 200:
        return response.text
    else:
        print(f"Ошибка при получении страницы. Код статуса: {response.status_code}")
        return None


def parse_schedule_row(row):
    pair_number_cell = row.find('td', class_='hd')
    if not pair_number_cell:
        return None, None, None, None

    pair_number = pair_number_cell.text.strip()
    day_of_week = pair_number[-4:-2] if len(pair_number) >= 4 else ''
    week = pair_number[-1] if len(pair_number) >= 1 else ''
    day = {
        'Вс': 'Воскресенье',
        'Сб': 'Суббота',
        'Пт': 'Пятница',
        'Чт': 'Четверг',
        'Ср': 'Среда',
        'Вт': 'Вторник',
        'Пн': 'Понедельник',
    }.get(day_of_week, '')

    current_day = None

    if '.' in pair_number:
        pair_number = pair_number[:-4]

        if current_day != day:
            if day == 'Понедельник':
                return f"\n⭐️ {day}, {pair_number}, {week} Неделя:\n", day, pair_number, week
            else:
                return f"\n⭐️ {day}, {pair_number}:\n", day, pair_number, week

    return None, day, pair_number, week


def parse_pair_info(pair_info_cell, user_settings):
    subject = pair_info_cell.find('a', class_='z1').text.strip()

    classroom_element = pair_info_cell.find('a', class_='z2')
    classroom = classroom_element.text.strip() if classroom_element and user_settings.get('settings_classroom', 1) else ""

    teacher_element = pair_info_cell.find('a', class_='z3')
    teacher = teacher_element.text.strip() if teacher_element and user_settings.get('settings_teacher', 1) else ""

    return subject, classroom, teacher


def generate_schedule_text(schedule_rows, user_settings):
    schedule_text = ""
    days_count = user_settings.get('settings_display_days', 7)

    day_counter = -1  # Счетчик дней

    for row in schedule_rows:
        schedule_row, current_day, pair_number, week = parse_schedule_row(row)

        if schedule_row:
            schedule_text += schedule_row
            day_counter += 1

        pair_info_cell = row.find('td', class_='ur')
        if pair_info_cell:
            subject, classroom, teacher = parse_pair_info(pair_info_cell, user_settings)

            if len(pair_number) > 3:
                pair_number = "1"

            schedule_text += f"— Пара {pair_number}: {subject}"
            if classroom and user_settings.get('settings_classroom', 1):
                schedule_text += f", {classroom}"
            if teacher and user_settings.get('settings_teacher', 1):
                schedule_text += f", {teacher}"

            schedule_text += "\n"

        if current_day and day_counter == days_count:
            break  # Прекращаем обработку после достижения указанного количества дней

    # Удаляем последние две строки
    schedule_text = '\n'.join(schedule_text.split('\n')[:-3])

    return schedule_text






