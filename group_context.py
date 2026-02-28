import aiosqlite
import json
import logging
from datetime import datetime
from collections import defaultdict, deque
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

class GroupContextManager:
    """Менеджер контекста для групповых чатов"""
    
    def __init__(self, db_path="group_memory.db", max_history_per_user=10):
        self.db_path = db_path
        self.max_history_per_user = max_history_per_user
        # Формат: self.user_history[chat_id][user_id] = deque(...)
        self.user_history = defaultdict(lambda: defaultdict(
            lambda: deque(maxlen=max_history_per_user)
        ))
        # Общая история чата (последние N сообщений)
        self.chat_history = defaultdict(lambda: deque(maxlen=30))
        
    async def init_db(self):
        """Инициализация базы данных"""
        async with aiosqlite.connect(self.db_path) as db:
            # Таблица для долгосрочной памяти о пользователях в чатах
            await db.execute('''
                CREATE TABLE IF NOT EXISTS chat_user_memory (
                    chat_id INTEGER,
                    user_id INTEGER,
                    user_info TEXT,  -- JSON с информацией о пользователе
                    facts TEXT,       -- JSON с фактами о пользователе
                    last_seen TIMESTAMP,
                    message_count INTEGER DEFAULT 0,
                    PRIMARY KEY (chat_id, user_id)
                )
            ''')
            
            # Таблица для статистики чата
            await db.execute('''
                CREATE TABLE IF NOT EXISTS chat_stats (
                    chat_id INTEGER PRIMARY KEY,
                    total_messages INTEGER DEFAULT 0,
                    active_users INTEGER DEFAULT 0,
                    last_activity TIMESTAMP
                )
            ''')
            await db.commit()
    
    def add_message(self, chat_id: int, user_id: int, user_name: str, 
                    message: str, is_bot_response: bool = False):
        """
        Добавляет сообщение в историю
        
        Args:
            chat_id: ID чата
            user_id: ID пользователя
            user_name: Имя пользователя
            message: Текст сообщения
            is_bot_response: Это ответ бота?
        """
        timestamp = datetime.now().isoformat()
        
        # Сохраняем в историю пользователя
        self.user_history[chat_id][user_id].append({
            "text": message,
            "timestamp": timestamp,
            "is_bot": is_bot_response
        })
        
        # Сохраняем в общую историю чата
        self.chat_history[chat_id].append({
            "user_id": user_id,
            "user_name": user_name,
            "text": message,
            "timestamp": timestamp,
            "is_bot": is_bot_response
        })
        
        logger.debug(f"💬 [{chat_id}] Сообщение от {user_name} ({user_id}) сохранено")
    
    def get_user_context(self, chat_id: int, user_id: int, 
                         max_messages: int = 5) -> str:
        """
        Возвращает контекст для конкретного пользователя
        
        Returns:
            Строка с историей диалога пользователя
        """
        if user_id not in self.user_history[chat_id]:
            return ""
        
        history = list(self.user_history[chat_id][user_id])
        if not history:
            return ""
        
        context_lines = ["📝 **История вашего общения со мной:**"]
        for msg in history[-max_messages:]:
            role = "Я" if msg["is_bot"] else "Вы"
            context_lines.append(f"{role}: {msg['text'][:100]}...")
        
        return "\n".join(context_lines)
    
    def get_chat_context(self, chat_id: int, max_messages: int = 10,
                         exclude_user_id: Optional[int] = None) -> str:
        """
        Возвращает общий контекст чата (последние сообщения всех участников)
        
        Args:
            chat_id: ID чата
            max_messages: Максимальное количество сообщений
            exclude_user_id: Исключить сообщения этого пользователя
                            (чтобы не дублировать его текущий вопрос)
        
        Returns:
            Строка с историей чата
        """
        history = list(self.chat_history[chat_id])
        if not history:
            return ""
        
        relevant = []
        for msg in reversed(history[-max_messages:]):
            if exclude_user_id and msg["user_id"] == exclude_user_id:
                continue
            relevant.insert(0, msg)  # Сохраняем хронологический порядок
        
        if not relevant:
            return ""
        
        context_lines = ["👥 **Недавние сообщения в чате:**"]
        for msg in relevant:
            name = msg["user_name"]
            if msg["is_bot"]:
                name = f"🤖 {name}"
            context_lines.append(f"{name}: {msg['text'][:100]}...")
        
        return "\n".join(context_lines)
    
    def get_combined_context(self, chat_id: int, user_id: int, 
                             user_name: str, current_message: str) -> Dict:
        """
        Формирует полный контекст для ответа
        
        Returns:
            Словарь с различными частями контекста
        """
        user_context = self.get_user_context(chat_id, user_id)
        chat_context = self.get_chat_context(chat_id, exclude_user_id=user_id)
        
        # Добавляем текущее сообщение в историю
        self.add_message(chat_id, user_id, user_name, current_message)
        
        return {
            "user_context": user_context,
            "chat_context": chat_context,
            "full_context": f"{user_context}\n\n{chat_context}" if user_context or chat_context else ""
        }
    
    async def save_user_info(self, chat_id: int, user_id: int, 
                              user_info: dict, facts: dict = None):
        """Сохраняет информацию о пользователе в БД"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO chat_user_memory (chat_id, user_id, user_info, facts, last_seen, message_count)
                VALUES (?, ?, ?, ?, ?, COALESCE((SELECT message_count FROM chat_user_memory 
                        WHERE chat_id = ? AND user_id = ?), 0) + 1)
                ON CONFLICT(chat_id, user_id) DO UPDATE SET
                    user_info = excluded.user_info,
                    facts = excluded.facts,
                    last_seen = excluded.last_seen,
                    message_count = message_count + 1
            ''', (
                chat_id, user_id, json.dumps(user_info, ensure_ascii=False),
                json.dumps(facts, ensure_ascii=False) if facts else None,
                datetime.now().isoformat(), chat_id, user_id
            ))
            await db.commit()
    
    async def get_user_stats(self, chat_id: int, user_id: int) -> dict:
        """Возвращает статистику пользователя в чате"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT message_count, facts FROM chat_user_memory WHERE chat_id = ? AND user_id = ?",
                (chat_id, user_id)
            )
            row = await cursor.fetchone()
            
            if row:
                return {
                    "message_count": row[0],
                    "facts": json.loads(row[1]) if row[1] else {}
                }
            return {"message_count": 0, "facts": {}}


# Создаем глобальный экземпляр
group_context = GroupContextManager()