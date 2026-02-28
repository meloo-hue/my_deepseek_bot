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

# Инициализация DeepSeek клиента (упрощенная версия)
client = AsyncOpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com"
)

MODEL_NAME = "deepseek-chat"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    bot_username = (await context.bot.get_me()).username
    await update.message.reply_text(
        f"🚀 Привет! Я бот **ШМЕЛЬ** на базе DeepSeek.\n\n"
        f"**Как со мной общаться:**\n"
        f"📱 В личных сообщениях — просто пиши\n"
        f"👥 В группах — упомяни меня @{bot_username}\n"
        f"💬 Или ответь на моё сообщение"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    user_message = update.message.text
    chat_type = update.effective_chat.type
    bot_username = (await context.bot.get_me()).username
    
    # Проверяем, нужно ли отвечать
    should_respond = False
    
    # Личный чат - отвечаем всегда
    if chat_type == "private":
        should_respond = True
        logger.info("💬 Личный чат, отвечаем")
    
    # Группа - только при упоминании или ответе
    elif chat_type in ["group", "supergroup"]:
        if f"@{bot_username}" in user_message:
            should_respond = True
            user_message = user_message.replace(f"@{bot_username}", "").strip()
            logger.info(f"👥 Упоминание в группе")
        elif (update.message.reply_to_message and 
              update.message.reply_to_message.from_user.id == context.bot.id):
            should_respond = True
            logger.info(f"🔄 Ответ на сообщение бота")
    
    if not should_respond:
        return
    
    if not user_message:
        await update.message.reply_text(
            "❓ Напишите вопрос после упоминания",
            reply_to_message_id=update.message.message_id
        )
        return
    
    # Показываем статус "печатает"
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, 
        action="typing"
    )
    
    try:
        logger.info(f"📤 Запрос к DeepSeek: {user_message[:100]}...")
        
        # Отправляем запрос к DeepSeek API
        response = await client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "Ты — полезный ассистент по имени Шмель."},
                {"role": "user", "content": user_message},
            ],
            temperature=0.7,
            max_tokens=2000,
        )
        
        bot_reply = response.choices[0].message.content
        logger.info(f"📥 Получен ответ от DeepSeek")
        
        await update.message.reply_text(
            bot_reply,
            reply_to_message_id=update.message.message_id if chat_type != "private" else None
        )
        
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        await update.message.reply_text(
            "😔 Извините, произошла ошибка.",
            reply_to_message_id=update.message.message_id if chat_type != "private" else None
        )

def main():
    """Запуск бота"""
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("🚀 Бот ШМЕЛЬ на базе DeepSeek запущен...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()