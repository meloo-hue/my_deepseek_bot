import asyncio
import sys
import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from openai import AsyncOpenAI

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
    raise ValueError("❌ Ошибка: Не найдены переменные окружения! Нужны TELEGRAM_TOKEN и DEEPSEEK_API_KEY")

# Инициализация DeepSeek клиента
client = AsyncOpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com"
)

MODEL_NAME = "deepseek-chat"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start - только для групп"""
    chat_type = update.effective_chat.type
    
    # Если это личный чат - просто игнорируем (даже не отвечаем)
    if chat_type == "private":
        logger.info(f"🚫 Игнорируем /start в личке от {update.effective_user.id}")
        return  # Молча выходим, НИЧЕГО не отправляем
    
    # Если это группа - приветствуем
    if chat_type in ["group", "supergroup"]:
        bot_username = (await context.bot.get_me()).username
        await update.message.reply_text(
            f"✅ Бот ШМЕЛЬ готов к работе в группе!\n"
            f"Упомяните меня @{bot_username} чтобы задать вопрос."
        )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений - ТОЛЬКО для групп"""
    chat_type = update.effective_chat.type
    
    # ❌ ВАЖНО: сразу отсекаем личные сообщения
    if chat_type == "private":
        # Даже не логируем каждое сообщение, чтобы не засорять логи
        # Можно закомментировать следующую строку, если хотите тишины
        logger.debug(f"Личное сообщение от {update.effective_user.id} проигнорировано")
        return  # Мгновенный выход, никакой обработки
    
    # ✅ Работаем только с группами
    if chat_type not in ["group", "supergroup"]:
        return  # На всякий случай, если есть другие типы чатов
    
    user_message = update.message.text
    bot_username = (await context.bot.get_me()).username
    chat_id = update.effective_chat.id
    
    # Проверяем упоминание бота
    if f"@{bot_username}" not in user_message:
        logger.debug(f"Группа {chat_id}: сообщение без упоминания")
        return
    
    # Убираем упоминание из сообщения
    user_message = user_message.replace(f"@{bot_username}", "").strip()
    
    # Если после удаления упоминания текст пустой
    if not user_message:
        await update.message.reply_text(
            "❓ Напишите вопрос после упоминания",
            reply_to_message_id=update.message.message_id
        )
        return
    
    logger.info(f"📤 Группа {chat_id}: запрос: {user_message[:50]}...")
    
    # Показываем статус "печатает"
    await context.bot.send_chat_action(
        chat_id=chat_id, 
        action="typing"
    )
    
    try:
        # Отправляем запрос к DeepSeek
        response = await client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "Ты — полезный ассистент по имени Шмель. Отвечай кратко и по делу."},
                {"role": "user", "content": user_message},
            ],
            temperature=0.7,
            max_tokens=2000,
        )
        
        bot_reply = response.choices[0].message.content
        logger.info(f"📥 Группа {chat_id}: получен ответ")
        
        # Отправляем ответ с цитированием
        await update.message.reply_text(
            bot_reply,
            reply_to_message_id=update.message.message_id
        )
        
    except Exception as e:
        logger.error(f"❌ Ошибка в группе {chat_id}: {e}")
        await update.message.reply_text(
            "😔 Извините, произошла ошибка.",
            reply_to_message_id=update.message.message_id
        )

def main():
    """Запуск бота"""
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Регистрируем обработчики
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("🚀 Бот ШМЕЛЬ на базе DeepSeek запущен...")
    logger.info("🔒 РЕЖИМ: ТОЛЬКО ГРУППЫ (личные сообщения ПОЛНОСТЬЮ игнорируются)")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()