import asyncio
import sys
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from google import genai  # Новая библиотека!
import logging

# Для Python 3.14+
if sys.version_info >= (3, 14):
    asyncio.set_event_loop(asyncio.new_event_loop())

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Конфигурация ---
TELEGRAM_TOKEN = "8039807556:AAG2e-gHgdJ98W1MRf_-SPFGVVgUYwTQFJ8"
GEMINI_API_KEY = "AIzaSyAsuRuME2x-CPllvs3iNG-aWY5jS0HRt6Q"

# Инициализируем клиента Gemini (новая библиотека!)
client = genai.Client(api_key=GEMINI_API_KEY)

# Выбираем модель (можно заменить на любую из вашего списка)
MODEL_NAME = "gemma-3-27b-it"  # Быстрая и современная модель

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Привет! Я бот на базе Gemini ({MODEL_NAME}). Задай мне любой вопрос!"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text

    try:
        # Показываем статус "печатает"
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action="typing"
        )

        logger.info(f"Запрос от пользователя: {user_message[:50]}...")

        # Отправляем запрос в Gemini (новый синтаксис!)
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=MODEL_NAME,
            contents=user_message
        )

        bot_reply = response.text
        logger.info(f"Получен ответ от Gemini")
        await update.message.reply_text(bot_reply)

    except Exception as e:
        logger.error(f"Ошибка при обращении к Gemini: {e}")
        await update.message.reply_text(
            "Извините, произошла ошибка при обработке запроса. Пожалуйста, попробуйте позже."
        )

def main():
    # Создаем приложение
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Регистрируем обработчики
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info(f"Бот с Gemini ({MODEL_NAME}) запущен...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()