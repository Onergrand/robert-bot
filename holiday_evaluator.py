# holiday_evaluator.py

from datetime import datetime, timedelta, date
from utils.constants import RUSSIAN_HOLIDAYS


class HolidayEvaluator:
    def __init__(self):
        self.today = datetime.today().date()
        self.today_str = self.today.strftime("%d-%m")
        self.year = self.today.year

    def evaluate(self):
        holidays_today = []

        for holiday in RUSSIAN_HOLIDAYS:
            if holiday['float_date']:
                float_date = self.get_floating_holiday_date(holiday['name'])
                if float_date == self.today:
                    holidays_today.append(holiday['name'])
            else:
                if holiday['date'] == self.today_str:
                    holidays_today.append(holiday['name'])

        return holidays_today

    def get_floating_holiday_date(self, name):
        """Определяет точную дату для плавающего праздника"""
        if name == "День программиста":
            return self.get_programmer_day()
        elif name == "Пасха (православная)":
            return self.orthodox_easter()
        elif name == "Масленица":
            return self.orthodox_easter() - timedelta(days=49)
        elif name == "Радоница":
            return self.orthodox_easter() + timedelta(days=9)
        elif name == "Троица (Пятидесятница)":
            return self.orthodox_easter() + timedelta(days=49)
        elif name == "День ПВО":
            return self.second_sunday_of_april()
        elif name == "День матери":
            return self.last_sunday_of_november()
        else:
            return None  # Неизвестный плавающий праздник

    def get_programmer_day(self):
        # 256-й день года (13 сентября или 12 в високосный год)
        day_of_year = 256
        return date(self.year, 1, 1) + timedelta(days=day_of_year - 1)

    def orthodox_easter(self):
        """Вычисляет дату православной Пасхи (алгоритм Meeus/Jones/Butcher)"""
        a = self.year % 19
        b = self.year % 7
        c = self.year % 4
        d = (19 * a + 15) % 30
        e = (2 * c + 4 * b + 6 * d + 6) % 7
        days = 22 + d + e
        if days > 31:
            return date(self.year, 5, days - 31)
        else:
            return date(self.year, 4, days)

    def second_sunday_of_april(self):
        d = date(self.year, 4, 1)
        while d.weekday() != 6:
            d += timedelta(days=1)
        return d + timedelta(weeks=1)

    def last_sunday_of_november(self):
        d = date(self.year, 11, 30)
        while d.weekday() != 6:
            d -= timedelta(days=1)
        return d
