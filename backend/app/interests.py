GROUPS = [
    ("Спорт", [
        ("football", "Футбол"), ("basketball", "Баскетбол"), ("volleyball", "Волейбол"), ("running", "Бег"),
        ("workout", "Тренировки"), ("swimming", "Плавание"), ("martial", "Единоборства"),
        ("skate", "Скейт и ролики"), ("bike", "Велосипед"), ("tabletennis", "Настольный теннис"),
        ("sport", "Другой спорт"),
    ]),
    ("Игры", [
        ("boardgames", "Настольные игры"), ("videogames", "Видеоигры"), ("chess", "Шахматы"),
        ("quiz", "Квизы и викторины"), ("games", "Другие игры"),
    ]),
    ("Музыка и творчество", [
        ("music", "Музыка"), ("singing", "Пение"), ("dance", "Танцы"), ("drawing", "Рисование"),
        ("theatre", "Театр"), ("photo", "Фотография"), ("video", "Съёмка видео"), ("creative", "Другое творчество"),
    ]),
    ("Учёба и наука", [
        ("study", "Учимся вместе"), ("exams", "Подготовка к ОГЭ и ЕГЭ"), ("olympiads", "Олимпиады"),
        ("languages", "Иностранные языки"), ("coding", "Программирование"), ("robotics", "Робототехника"),
        ("science", "Наука и опыты"), ("reading", "Книги"),
    ]),
    ("Проекты и дела", [
        ("projects", "Проекты"), ("volunteering", "Волонтёрство"), ("school_events", "Школьные мероприятия"),
        ("business", "Свои идеи и бизнес"),
    ]),
    ("Отдых и общение", [
        ("hangout", "Просто пообщаться"), ("walks", "Прогулки"), ("hiking", "Походы"), ("cinema", "Кино"),
        ("cooking", "Готовим вместе"), ("travel", "Поездки"),
    ]),
]

INTERESTS = {id_: name for _, items in GROUPS for id_, name in items}


def interests_out() -> list[dict]:
    return [{"id": id_, "name": name, "group": group} for group, items in GROUPS for id_, name in items]
