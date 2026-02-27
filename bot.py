import asyncio
import sys
import os  # 👈 ОБЯЗАТЕЛЬНО ДОБАВЬТЕ ЭТОТ ИМПОРТ!
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

# --- Читаем переменные окружения (БЕЗОПАСНО!) ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Проверяем, что ключи найдены
if not TELEGRAM_TOKEN:
    raise ValueError("❌ Ошибка: Не найдена переменная окружения TELEGRAM_TOKEN!")
if not GEMINI_API_KEY:
    raise ValueError("❌ Ошибка: Не найдена переменная окружения GEMINI_API_KEY!")

logger.info("✅ Ключи успешно загружены из переменных окружения")

# Инициализируем Gemini клиент
client = genai.Client(api_key=GEMINI_API_KEY)
MODEL_NAME = "gemma-3-27b-it"

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