import asyncio
import sys
import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from openai import AsyncOpenAI  # DeepSeek использует OpenAI-совместимый клиент

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
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")  # Переименовали переменную

if not TELEGRAM_TOKEN or not DEEPSEEK_API_KEY:
    raise ValueError("❌ Ошибка: Не найдены переменные окружения! Нужны TELEGRAM_TOKEN и DEEPSEEK_API_KEY")

# Инициализация DeepSeek клиента (OpenAI-совместимый)
client = AsyncOpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com"  # Важно: указываем API DeepSeek
)

# Модель DeepSeek
MODEL_NAME = "deepseek-chat"  # Основная модель DeepSeek
# Альтернативы: "deepseek-coder" для программирования, "deepseek-reasoner" для сложных задач

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    bot_username = (await context.bot.get_me()).username
    await update.message.reply_text(
        f"🚀 Привет! Я бот **ШМЕЛЬ** на базе DeepSeek.\n\n"
        f"**Что я умею:**\n"
        f"• Отвечаю на любые вопросы\n"
        f"• Помогаю с программированием\n"
        f"• Анализирую тексты\n\n"
        f"**Как со мной общаться:**\n"
        f"📱 В личных сообщениях — просто пиши\n"
        f"👥 В группах — упомяни меня @{bot_username}\n"
        f"💬 Или ответь на моё сообщение\n\n"
        f"_Мной управляет модель DeepSeek, которая считается одной из лучших для логики и кода!_"
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
        # Упоминание бота
        if f"@{bot_username}" in user_message:
            should_respond = True
            # Убираем упоминание из сообщения
            user_message = user_message.replace(f"@{bot_username}", "").strip()
            logger.info(f"👥 Упоминание бота в группе {update.effective_chat.id}")
        
        # Ответ на сообщение бота
        elif (update.message.reply_to_message and 
              update.message.reply_to_message.from_user.id == context.bot.id):
            should_respond = True
            logger.info(f"🔄 Ответ на сообщение бота в группе {update.effective_chat.id}")
    
    if not should_respond:
        logger.debug("Игнорируем сообщение (нет триггера)")
        return
    
    # Если после удаления упоминания текст пустой
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
                {
                    "role": "system", 
                    "content": "Ты — полезный ассистент по имени Шмель. Отвечай кратко, по делу и дружелюбно. "
                               "Ты основан на модели DeepSeek, которая отлично справляется с логикой и программированием."
                },
                {"role": "user", "content": user_message},
            ],
            temperature=0.7,  # Можно регулировать креативность (0.0 - 2.0)
            max_tokens=2000,  # Максимальная длина ответа
            top_p=0.95,
            frequency_penalty=0.0,
            presence_penalty=0.0,
        )
        
        # Получаем ответ
        bot_reply = response.choices[0].message.content
        logger.info(f"📥 Получен ответ от DeepSeek ({len(bot_reply)} символов)")
        
        # Отправляем ответ (с цитированием в группах для удобства)
        await update.message.reply_text(
            bot_reply,
            reply_to_message_id=update.message.message_id if chat_type != "private" else None
        )
        
    except Exception as e:
        logger.error(f"❌ Ошибка при обращении к DeepSeek: {e}", exc_info=True)
        
        # Понятное сообщение об ошибке пользователю
        error_message = "😔 Извините, произошла ошибка при обработке запроса."
        
        if "insufficient_quota" in str(e) or "402" in str(e):
            error_message = "⚠️ Превышен лимит запросов к DeepSeek API. Попробуйте позже."
        elif "rate_limit" in str(e).lower():
            error_message = "⏱️ Слишком много запросов. Подождите немного и повторите."
        elif "invalid_api_key" in str(e).lower():
            error_message = "🔑 Ошибка авторизации DeepSeek. Администратор уже знает о проблеме."
            logger.critical("Неверный API ключ DeepSeek!")
        
        await update.message.reply_text(
            error_message,
            reply_to_message_id=update.message.message_id if chat_type != "private" else None
        )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Глобальный обработчик ошибок"""
    logger.error(f"Ошибка при обработке обновления {update}: {context.error}")

def main():
    """Запуск бота"""
    # Создаем приложение
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Регистрируем обработчики
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Регистрируем глобальный обработчик ошибок
    app.add_error_handler(error_handler)
    
    # Логируем информацию о запуске
    logger.info("🚀 Запуск бота ШМЕЛЬ на базе DeepSeek...")
    logger.info(f"🤖 Модель: {MODEL_NAME}")
    logger.info(f"📱 Режим: личные сообщения + группы (с упоминанием)")
    
    # Запускаем бота
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()