import asyncio
import sys
import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from google import genai

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Конфигурация из переменных окружения ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
    raise ValueError("❌ Ошибка: Не найдены переменные окружения!")

# Инициализация Gemini
client = genai.Client(api_key=GEMINI_API_KEY)
MODEL_NAME = "gemma-3-27b-it"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я бот  ШМЕЛЬ.\n\n"
        "В личных сообщениях я отвечаю на все вопросы.\n"
        "В группах — только если меня упомянуть (@username) или ответить на моё сообщение."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    chat_type = update.effective_chat.type
    bot_username = (await context.bot.get_me()).username
    
    # Проверяем, нужно ли отвечать
    should_respond = False
    
    # Личный чат - отвечаем всегда
    if chat_type == "private":
        should_respond = True
        logger.info("Личный чат, отвечаем")
    
    # Группа - только при упоминании или ответе
    elif chat_type in ["group", "supergroup"]:
        # Упоминание бота
        if f"@{bot_username}" in user_message:
            should_respond = True
            user_message = user_message.replace(f"@{bot_username}", "").strip()
            logger.info("Упоминание бота в группе")
        
        # Ответ на сообщение бота
        elif (update.message.reply_to_message and 
              update.message.reply_to_message.from_user.id == context.bot.id):
            should_respond = True
            logger.info("Ответ на сообщение бота")
    
    if not should_respond:
        logger.info("Игнорируем сообщение (нет триггера)")
        return
    
    # Показываем статус "печатает"
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, 
        action="typing"
    )
    
    try:
        logger.info(f"Запрос: {user_message[:50]}...")
        
        # Отправляем в Gemini
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=MODEL_NAME,
            contents=user_message
        )
        
        bot_reply = response.text
        logger.info("Получен ответ от Gemini")
        await update.message.reply_text(bot_reply)
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text("Извините, произошла ошибка.")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info(f"Бот с Gemini ({MODEL_NAME}) запущен...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()