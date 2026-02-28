python
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
    """Обработчик команды /start"""
    chat_type = update.effective_chat.type
    bot_username = (await context.bot.get_me()).username
    
    # В личных сообщениях объясняем, что бот только для групп
    if chat_type == "private":
        await update.message.reply_text(
            f"❌ **Этот бот работает только в группах!**\n\n"
            f"Чтобы использовать меня:\n"
            f"1️⃣ Добавьте меня в группу\n"
            f"2️⃣ Упомяните меня @{bot_username} с вашим вопросом\n\n"
            f"Пример: @{bot_username} Какая сегодня погода?"
        )
        return
    
    # В группах короткое приветствие
    await update.message.reply_text(
        f"✅ Бот ШМЕЛЬ готов к работе!\n"
        f"Упомяните меня @{bot_username} чтобы задать вопрос."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    chat_type = update.effective_chat.type
    
    # ❌ ПОЛНОСТЬЮ ИГНОРИРУЕМ ЛИЧНЫЕ СООБЩЕНИЯ
    if chat_type == "private":
        # Просто логируем и ничего не отвечаем
        logger.info(f"🚫 Заблокировано личное сообщение от {update.effective_user.id}")
        return  # Молча выходим, бот ничего не отправляет
    
    # ✅ РАБОТАЕМ ТОЛЬКО В ГРУППАХ
    if chat_type in ["group", "supergroup"]:
        user_message = update.message.text
        bot_username = (await context.bot.get_me()).username
        chat_id = update.effective_chat.id
        
        # Проверяем упоминание бота
        if f"@{bot_username}" not in user_message:
            logger.info(f"Группа {chat_id}: сообщение без упоминания — игнорируем")
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
            logger.info(f"📥 Получен ответ от DeepSeek")
            
            # Отправляем ответ с цитированием
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

def main():
    """Запуск бота"""
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Регистрируем обработчики
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("🚀 Бот ШМЕЛЬ на базе DeepSeek запущен...")
    logger.info("🔒 Режим: ТОЛЬКО ГРУППЫ (личные сообщения игнорируются)")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()