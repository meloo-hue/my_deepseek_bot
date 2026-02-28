import aiosqlite
import json
import logging
from datetime import datetime, timedelta
from collections import deque

logger = logging.getLogger(__name__)

class BotMemory:
    """Класс для управления памятью бота"""
    
    def __init__(self, db_path="bot_memory.db"):
        self.db_path = db_path
        self.short_term = {}
        self.max_short_term = 10
        
    async def init_db(self):
        """Инициализация базы данных"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS user_memory (
                    user_id INTEGER PRIMARY KEY,
                    facts TEXT,
                    last_seen TIMESTAMP,
                    total_messages INTEGER DEFAULT 0
                )
            ''')
            
            await db.execute('''
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    role TEXT,
                    message TEXT,
                    timestamp TIMESTAMP
                )
            ''')
            await db.commit()
    
    def add_to_short_term(self, user_id: int, role: str, message: str):
        """Добавляет сообщение в краткосрочную память"""
        if user_id not in self.short_term:
            self.short_term[user_id] = deque(maxlen=self.max_short_term)
        
        self.short_term[user_id].append({
            "role": role,
            "content": message,
            "timestamp": datetime.now().isoformat()
        })
        
        logger.debug(f"💭 Добавлено в краткосрочную память для {user_id}: {role}")
    
    def get_short_term(self, user_id: int, limit: int = 5) -> list:
        """Возвращает последние N сообщений из краткосрочной памяти"""
        if user_id not in self.short_term:
            return []
        
        messages = list(self.short_term[user_id])
        return messages[-limit:]
    
    def get_conversation_context(self, user_id: int, max_messages: int = 5) -> str:
        """Формирует контекст для отправки в DeepSeek"""
        recent = self.get_short_term(user_id, max_messages)
        
        if not recent:
            return ""
        
        context_lines = ["\n**Последние сообщения в диалоге:**"]
        for msg in recent[:-1]:
            prefix = "Пользователь" if msg["role"] == "user" else "Шмель"
            context_lines.append(f"{prefix}: {msg['content'][:100]}...")
        
        return "\n".join(context_lines)
    
    async def remember_fact(self, user_id: int, fact_key: str, fact_value: str):
        """Запоминает факт о пользователе"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT facts FROM user_memory WHERE user_id = ?",
                (user_id,)
            )
            row = await cursor.fetchone()
            
            facts = {}
            if row and row[0]:
                facts = json.loads(row[0])
            
            facts[fact_key] = {
                "value": fact_value,
                "updated": datetime.now().isoformat()
            }
            
            await db.execute('''
                INSERT INTO user_memory (user_id, facts, last_seen, total_messages)
                VALUES (?, ?, ?, COALESCE((SELECT total_messages FROM user_memory WHERE user_id = ?), 0) + 1)
                ON CONFLICT(user_id) DO UPDATE SET
                    facts = excluded.facts,
                    last_seen = excluded.last_seen,
                    total_messages = total_messages + 1
            ''', (user_id, json.dumps(facts), datetime.now().isoformat(), user_id))
            
            await db.commit()
            logger.info(f"🧠 Запомнил факт о {user_id}: {fact_key} = {fact_value}")
    
    async def get_user_facts(self, user_id: int) -> dict:
        """Возвращает все сохраненные факты о пользователе"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT facts FROM user_memory WHERE user_id = ?",
                (user_id,)
            )
            row = await cursor.fetchone()
            
            if row and row[0]:
                return json.loads(row[0])
            return {}
    
    async def extract_facts_from_message(self, user_id: int, message: str):
        """Пытается извлечь факты из сообщения пользователя"""
        message_lower = message.lower()
        
        if "меня зовут" in message_lower:
            parts = message_lower.split("меня зовут")
            if len(parts) > 1:
                name = parts[1].strip().split()[0].capitalize()
                await self.remember_fact(user_id, "name", name)
        
        if "я из" in message_lower or "живу в" in message_lower:
            words = message_lower.split()
            for i, word in enumerate(words):
                if word in ["из", "в"] and i + 1 < len(words):
                    city = words[i + 1].strip(".,!?").capitalize()
                    if len(city) > 2:
                        await self.remember_fact(user_id, "city", city)
        
        interests = ["люблю", "нравится", "увлекаюсь", "работаю"]
        for interest in interests:
            if interest in message_lower:
                idx = message_lower.find(interest) + len(interest)
                if idx < len(message_lower):
                    topic = message[idx:].split('.')[0].split(',')[0].strip()
                    if len(topic) > 3:
                        await self.remember_fact(user_id, "interest", topic)
    
    async def get_user_context(self, user_id: int) -> str:
        """Формирует контекст из долгосрочной памяти"""
        facts = await self.get_user_facts(user_id)
        
        if not facts:
            return ""
        
        context_lines = ["\n**Что я знаю о пользователе:**"]
        for key, fact in facts.items():
            if key == "name":
                context_lines.append(f"- Его/ее зовут {fact['value']}")
            elif key == "city":
                context_lines.append(f"- Он/она из {fact['value']}")
            elif key == "interest":
                context_lines.append(f"- Он/она интересуется {fact['value']}")
            else:
                context_lines.append(f"- {key}: {fact['value']}")
        
        return "\n".join(context_lines)