import asyncio
import sys
import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from openai import AsyncOpenAI
from memory import BotMemory  # 👈 Импортируем наш модуль памяти

# Для Python 3.14+
if sys.version_info >= (3, 14):
    asyncio.set_event_loop(asyncio.new_event_loop())

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Конфигурация из переменных окружения ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")

if not TELEGRAM_TOKEN or not DEEPSEEK_API_KEY:
    raise ValueError("❌ Ошибка: Не найдены переменные окружения!")

# Инициализация DeepSeek клиента
client = AsyncOpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com"
)

MODEL_NAME = "deepseek-chat"

# Инициализация памяти
memory = BotMemory()

async def init_memory():
    """Инициализация базы данных при запуске"""
    await memory.init_db()
    logger.info("🧠 Система памяти инициализирована")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    chat_type = update.effective_chat.type
    user_id = update.effective_user.id
    
    # Игнорируем личные сообщения
    if chat_type == "private":
        logger.info(f"🚫 Игнорируем /start в личке от {user_id}")
        return
    
    # Для групп - приветствие с информацией о памяти
    bot_username = (await context.bot.get_me()).username
    
    # Проверяем, знаем ли мы этого пользователя
    facts = await memory.get_user_facts(user_id)
    greeting = "С возвращением" if facts else "Привет"
    
    await update.message.reply_text(
        f"{greeting}! Я бот ШМЕЛЬ.\n\n"
        f"🧠 **Я теперь с памятью!**\n"
        f"• Помню последние сообщения в диалоге\n"
        f"• Запоминаю факты о вас (имя, город, интересы)\n\n"
        f"**Как использовать:**\n"
        f"Упомяните меня @{bot_username} с вопросом\n\n"
        f"**Примеры:**\n"
        f"• @{bot_username} меня зовут Александр\n"
        f"• @{bot_username} что ты обо мне знаешь?\n"
        f"• @{bot_username} какой у меня любимый цвет?"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    chat_type = update.effective_chat.type
    
    # Игнорируем личные сообщения
    if chat_type == "private":
        return
    
    # Работаем только с группами
    if chat_type not in ["group", "supergroup"]:
        return
    
    user_message = update.message.text
    bot_username = (await context.bot.get_me()).username
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    # Проверяем упоминание бота
    if f"@{bot_username}" not in user_message:
        return
    
    # Убираем упоминание
    user_message = user_message.replace(f"@{bot_username}", "").strip()
    
    if not user_message:
        await update.message.reply_text(
            "❓ Напишите вопрос после упоминания",
            reply_to_message_id=update.message.message_id
        )
        return
    
    # Показываем статус "печатает"
    await context.bot.send_chat_action(
        chat_id=chat_id, 
        action="typing"
    )
    
    # 🔍 Пытаемся извлечь факты из сообщения
    await memory.extract_facts_from_message(user_id, user_message)
    
    # 📝 Получаем контекст из памяти
    short_context = memory.get_conversation_context(user_id)
    user_context = await memory.get_user_context(user_id)
    
    # Сохраняем сообщение пользователя в краткосрочную память
    memory.add_to_short_term(user_id, "user", user_message)
    
    logger.info(f"📤 Группа {chat_id}: запрос от {user_id}: {user_message[:50]}...")
    
    try:
        # Формируем системный промпт с контекстом
        system_content = "Ты — полезный ассистент по имени Шмель. Отвечай кратко и по делу."
        
        if user_context:
            system_content += f"\n\n{user_context}"
        
        if short_context:
            system_content += f"\n\n{short_context}"
        
        # Отправляем запрос к DeepSeek
        response = await client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_message},
            ],
            temperature=0.7,
            max_tokens=2000,
        )
        
        bot_reply = response.choices[0].message.content
        logger.info(f"📥 Группа {chat_id}: получен ответ")
        
        # Сохраняем ответ бота в память
        memory.add_to_short_term(user_id, "assistant", bot_reply)
        
        await update.message.reply_text(
            bot_reply,
            reply_to_message_id=update.message.message_id
        )
        
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        await update.message.reply_text(
            "😔 Извините, произошла ошибка.",
            reply_to_message_id=update.message.message_id
        )

async def post_init(application: Application):
    """Действия после инициализации бота"""
    await init_memory()

def main():
    """Запуск бота"""
    app = Application.builder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("🚀 Бот ШМЕЛЬ на базе DeepSeek запущен...")
    logger.info("🧠 Режим: с памятью (краткосрочная + долгосрочная)")
    logger.info("🔒 Только группы")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()