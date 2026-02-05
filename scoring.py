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
import os
import re
import time
import json
import logging
import requests
from typing import Optional, List, Dict
from telegram import Update

# Регулярка для определения смеха (пример: "ахах", "ха-ха", "ахахах")
LAUGHTER_PATTERN = re.compile(r"\b(ха|хах|ахах)+\b", re.IGNORECASE)

class Scorer:
    def __init__(self, chat_data: dict, bot_username: str, bot_id: int, api_key: Optional[str] = None):
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
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")

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

    def _call_deepseek_reasoning(self, message_text: str, context: Optional[List[Dict[str, str]]] = None) -> Optional[dict]:
        """
        Вызывает DeepSeek reasoning модель для оценки необходимости ответа на сообщение.
        Возвращает словарь с ключами:
        - should_respond: bool - нужно ли отвечать
        - reasoning: str - reasoning процесс модели
        - confidence: float - уверенность (0.0-1.0), если доступно
        Возвращает None в случае ошибки.
        """
        if not self.api_key:
            logging.warning("[SCORING] DEEPSEEK_API_KEY not set, skipping reasoning evaluation")
            return None

        url = "https://api.deepseek.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        # Формируем промпт для reasoning модели
        system_prompt = """Ты помощник для оценки сообщений в чате. Твоя задача - определить, нужно ли боту отвечать на сообщение.

Проанализируй сообщение и определи:
1. Обращается ли автор к боту напрямую или косвенно?
2. Есть ли в сообщении вопрос, требующий ответа?
3. Является ли сообщение частью активной дискуссии, где ответ бота будет уместен?
4. Есть ли в сообщении что-то интересное, на что стоит отреагировать?
Темы интересные для бота - СВО, Украина, Имена и прозвища(Артем, Никон, Никонов, Андрей, Матвей, 
Усков, Тимоха, ботинок, старый, Савва, Савелий, шишка, швецов, АШ, Илю, Илья, Ведегава, Веденеев), 
план 28, аниме, туалеты, сглыпа, игры, вар тандер, данила, кэн, кожемяк, кожемяка, даня, письки

Ответь в формате JSON:
{
  "should_respond": true/false,
  "reasoning": "твой процесс рассуждения",
  "confidence": 0.0-1.0
}

Будь строгим - отвечай только если сообщение действительно требует ответа или очень интересное."""

        user_prompt = f"Сообщение для оценки: \"{message_text}\""
        
        # Добавляем контекст, если есть
        messages = [{"role": "system", "content": system_prompt}]
        if context:
            # Берем последние 5 сообщений для контекста
            messages.extend(context[-15:])
        messages.append({"role": "user", "content": user_prompt})

        # Пробуем сначала reasoning модель, если не работает - fallback на обычную
        models_to_try = ["deepseek-chat", "deepseek-reasoner"]
        
        for model_name in models_to_try:
            data = {
                "model": model_name,
                "messages": messages,
                "stream": False,
                "temperature": 0.3,  # Низкая температура для более детерминированных ответов
            }

            try:
                response = requests.post(
                    url,
                    headers=headers,
                    json=data,
                    timeout=10
                )
                response.raise_for_status()
                result = response.json()
                
                # Извлекаем ответ модели
                content = result["choices"][0]["message"]["content"]
                
                # Пытаемся распарсить JSON из ответа
                # Ищем JSON в ответе (может быть обернут в markdown или текст)
                json_match = re.search(r'\{[^{}]*"should_respond"[^{}]*\}', content, re.DOTALL)
                if json_match:
                    try:
                        parsed = json.loads(json_match.group(0))
                        return {
                            "should_respond": bool(parsed.get("should_respond", False)),
                            "reasoning": parsed.get("reasoning", content),
                            "confidence": float(parsed.get("confidence", 0.5))
                        }
                    except (json.JSONDecodeError, ValueError):
                        pass
                
                # Если не удалось распарсить JSON, пытаемся извлечь информацию из текста
                should_respond = "should_respond" in content.lower() and ("true" in content.lower() or "да" in content.lower() or "yes" in content.lower())
                return {
                    "should_respond": should_respond,
                    "reasoning": content,
                    "confidence": 0.5
                }

            except requests.exceptions.Timeout:
                logging.warning(f"[SCORING] DeepSeek {model_name} timeout, trying next model")
                continue
            except requests.exceptions.RequestException as e:
                # Если модель не найдена (404), пробуем следующую
                if hasattr(e, 'response') and e.response is not None and e.response.status_code == 404:
                    logging.debug(f"[SCORING] Model {model_name} not found, trying next")
                    continue
                logging.warning(f"[SCORING] DeepSeek {model_name} API error: {e}, trying next model")
                continue
            except Exception as e:
                logging.warning(f"[SCORING] Error with {model_name}: {e}, trying next model")
                continue
        
        # Если все модели не сработали
        logging.warning("[SCORING] All DeepSeek models failed")
        return None

    def evaluate(self, update: Update, context_history: Optional[List[Dict[str, str]]] = None) -> dict:
        """
        Оценивает сообщение. Возвращает словарь с ключами:
          - respond: bool
          - mode: 'immediate', 'delayed', 'laughter', 'context_check'
          - delay: int (секунды) для режима 'delayed'
        """
        chat = update.effective_chat
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

        if chat.type == 'private':
                    logging.info(f"[SCORING] Private chat detected (ID: {chat.id}), responding always.")
                    return {
                        'respond': True, 
                        'mode': 'immediate', 
                        'reason': 'private_chat'
                    }

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
        # if laughter:
        #     self.responded.add(msg_id)
        #     return {'respond': True, 'mode': 'laughter'}

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

        # 5.4 Проверка через DeepSeek reasoning модель
        # Используем reasoning для оценки сообщений, которые не попали под явные критерии
        if text.strip():  # Только если есть текст для анализа
            reasoning_result = self._call_deepseek_reasoning(text, context_history)
            if reasoning_result and reasoning_result.get('should_respond', False):
                confidence = reasoning_result.get('confidence', 0.5)
                # Отвечаем только если уверенность достаточно высока
                if confidence >= 0.6:
                    self.responded.add(msg_id)
                    logging.info(f"[SCORING] Reasoning decision: respond=True, confidence={confidence:.2f}, reasoning={reasoning_result.get('reasoning', '')[:100]}")
                    return {'respond': True, 'mode': 'immediate', 'reasoning': reasoning_result.get('reasoning', '')}
                else:
                    logging.debug(f"[SCORING] Reasoning decision: respond=False (low confidence {confidence:.2f})")

        # 5.5 Каждые 10 сообщений делаем контекстную проверку
        if count % 2 == 0:
            return {'respond': False, 'mode': 'context_check'}

        # 5.6 По умолчанию — не отвечаем
        return {'respond': False}
