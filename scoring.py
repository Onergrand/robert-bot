# scoring.py
"""
Модуль для оценки сообщений и принятия решения, нужно ли боту отвечать.
Используется в основном файле (main.py) через:
    from scoring import Scorer

Пример использования в handle_message:
    scorer = Scorer(context.chat_data, context.bot_data['bot_username'], context.bot.id)
    decision = scorer.evaluate(update)
    if decision.get('respond'):
        # в зависимости от decision['mode']:
        # - 'immediate' или 'laughter' => отвечаем сразу
        # - 'delayed' => планируем ответ через decision['delay'] секунд
        pass

Данный модуль хранит в chat_data структуры:
- scoring.reply_counts: число ответов других пользователей на каждое сообщение
- scoring.reaction_counts: число реакций на каждое сообщение (вы должны обновлять извне)
- scoring.responded: множество message_id, на которые бот уже отвечал
- scoring.user_streaks: для каждого пользователя (user_id) пара (текущий стрик, время последнего сообщения)
- scoring.message_counter: общее число полученных сообщений в чате
"""
import re
import time
from telegram import Update

# Регулярка для определения смеха (пример: "ахах", "ха-ха", "ахахах")
LAUGHTER_PATTERN = re.compile(r"\b(ха|хах|ахах)+\b", re.IGNORECASE)

class Scorer:
    def __init__(self, chat_data: dict, bot_username: str, bot_id: int):
        # Инициализация структур в chat_data
        scoring = chat_data.setdefault('scoring', {})
        self.reply_counts = scoring.setdefault('reply_counts', {})
        self.reaction_counts = scoring.setdefault('reaction_counts', {})
        self.responded = scoring.setdefault('responded', set())
        self.user_streaks = scoring.setdefault('user_streaks', {})
        self.message_counter = scoring.setdefault('message_counter', 0)
        self.last_streak_response_time = scoring.setdefault('last_streak_response_time', 0)

        self.bot_username = bot_username.lower()
        self.bot_id = bot_id

    def record_reply(self, update: Update):
        msg = update.message
        # Если кто-то отвечает на чужое сообщение (не бот), считаем
        if msg.reply_to_message and msg.from_user.id != self.bot_id:
            orig_id = msg.reply_to_message.message_id
            self.reply_counts[orig_id] = self.reply_counts.get(orig_id, 0) + 1

    def record_reaction(self, message_id: int, count: int):
        # Вызывать из внешнего хендлера реакций, чтобы обновить число реакций
        self.reaction_counts[message_id] = count

    def update_user_streak(self, update: Update) -> int:
        user_id = update.message.from_user.id
        now = time.time()
        streak, last_time = self.user_streaks.get(user_id, (0, 0))
        # Если в пределах 2 минут — продолжаем стрик, иначе сбрасываем
        if now - last_time < 120:
            streak += 1
        else:
            streak = 1
        self.user_streaks[user_id] = (streak, now)
        return streak

    def increment_message_counter(self) -> int:
        self.message_counter += 1
        return self.message_counter

    def evaluate(self, update: Update) -> dict:
        """
        Оценивает сообщение. Возвращает словарь с ключами:
          - respond: bool
          - mode: 'immediate', 'delayed', 'laughter', 'context_check'
          - delay: int (секунды) для режима 'delayed'
        """
        msg = update.message
        msg_id = msg.message_id
        user_id = msg.from_user.id
        text = msg.text or ''

        # 1) Никогда не отвечаем себе
        if user_id == self.bot_id:
            return {'respond': False}

        # 2) Обновляем метрики
        self.record_reply(update)
        streak = self.update_user_streak(update)
        count = self.increment_message_counter()

        # 3) Если уже отвечали на это сообщение — пропускаем
        if msg_id in self.responded:
            return {'respond': False}

        # 4) Извлекаем признаки
        direct_reply = bool(msg.reply_to_message and msg.reply_to_message.from_user.id == self.bot_id)
        mention = ('@' + self.bot_username) in text.lower() or 'роберт' in text.lower()
        many_replies = self.reply_counts.get(msg_id, 0) >= 2
        reaction_and_reply = (self.reply_counts.get(msg_id, 0) >= 1 and self.reaction_counts.get(msg_id, 0) >= 1)
        laughter = bool(LAUGHTER_PATTERN.search(text))

        # 5) Логика принятия решения
        # 5.1 Смех — всегда коротко ответить/посмеяться
        if laughter:
            self.responded.add(msg_id)
            return {'respond': True, 'mode': 'laughter'}

        # 5.2 Прямой реплай, упоминание, кол-во ответов, реакция+ответ
        if direct_reply or mention or many_replies or reaction_and_reply:
            self.responded.add(msg_id)
            return {'respond': True, 'mode': 'immediate'}

        # 5.3 Стрик автора >=3 => отложенный ответ, не чаще чем раз в 180 секунд
        if streak >= 3:
            now = time.time()
            if now - self.last_streak_response_time >= 180:
                self.last_streak_response_time = now
                self.responded.add(msg_id)
                return {'respond': True, 'mode': 'delayed', 'delay': 60}


        # 5.4 Каждые 10 сообщений делаем контекстную проверку
        if count % 10 == 0:
            return {'respond': False, 'mode': 'context_check'}

        # 5.5 По умолчанию — не отвечаем
        return {'respond': False}
