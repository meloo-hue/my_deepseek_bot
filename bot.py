import asyncio
import sys
import os
import logging
import json
import aiohttp
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from openai import AsyncOpenAI
from memory import BotMemory
from group_context import group_context
from tavily_search import tavily_search  # Поисковый движок
from rss_news import rss_news  # 👈 Добавлен RSS-движок

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
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
WEATHER_API_KEY = os.environ.get("WEATHER_API_KEY")
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY")
# Для RSS не нужен API ключ - он бесплатный!

if not TELEGRAM_TOKEN or not DEEPSEEK_API_KEY:
    raise ValueError("❌ Ошибка: Не найдены TELEGRAM_TOKEN или DEEPSEEK_API_KEY")

# Инициализация DeepSeek
client = AsyncOpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com"
)

MODEL_NAME = "deepseek-chat"

# Память
memory = BotMemory()

# Инициализация Tavily (если есть ключ)
if TAVILY_API_KEY:
    tavily_search.initialize(TAVILY_API_KEY)
    logger.info("🔍 Tavily поиск инициализирован")

# RSS новости инициализируются автоматически (без ключа)
logger.info("📰 RSS новости инициализированы (бесплатно, безлимитно)")

# ========== ФУНКЦИЯ ПОГОДЫ ==========

async def get_weather_from_api(city: str) -> str:
    """Реальная функция, вызывающая API погоды"""
    if not WEATHER_API_KEY:
        return "Ошибка: API ключ погоды не настроен"
    
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric&lang=ru"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    weather_desc = data['weather'][0]['description']
                    temp = data['main']['temp']
                    feels_like = data['main']['feels_like']
                    humidity = data['main']['humidity']
                    wind = data['wind']['speed']
                    
                    return json.dumps({
                        "city": data['name'],
                        "country": data['sys']['country'],
                        "description": weather_desc,
                        "temperature": temp,
                        "feels_like": feels_like,
                        "humidity": humidity,
                        "wind_speed": wind
                    }, ensure_ascii=False)
                elif response.status == 404:
                    return json.dumps({"error": f"Город '{city}' не найден"}, ensure_ascii=False)
                else:
                    return json.dumps({"error": "Ошибка сервиса погоды"}, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Ошибка API погоды: {e}")
        return json.dumps({"error": "Ошибка при запросе погоды"}, ensure_ascii=False)


# ========== ОПИСАНИЕ ФУНКЦИИ ДЛЯ DEEPSEEK ==========

weather_tool = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Получить текущую погоду в указанном городе",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "Название города на русском или английском, например: Москва, London"
                }
            },
            "required": ["city"]
        }
    }
}

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========

async def init_memory():
    """Инициализация памяти"""
    await memory.init_db()
    await group_context.init_db()
    logger.info("🧠 Память и групповой контекст инициализированы")

# ========== КОМАНДА HELP ==========

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает все доступные команды бота"""
    chat_type = update.effective_chat.type
    if chat_type == "private":
        return
    
    bot_username = (await context.bot.get_me()).username
    weather_status = "✅" if WEATHER_API_KEY else "❌"
    search_status = "✅" if TAVILY_API_KEY else "❌"
    
    help_text = (
        f"🤖 **ШМЕЛЬ — список команд**\n\n"
        
        f"**📋 Основные команды:**\n"
        f"• `/start` - приветствие и информация о боте\n"
        f"• `/help` - показать это меню\n"
        f"• `/context` - показать текущий контекст чата\n\n"
        
        f"**📰 RSS Новости (бесплатно, безлимитно):**\n"
        f"• `/news` - свежие новости\n"
        f"• `/news [запрос]` - поиск новостей\n"
        f"• `/sources` - список всех источников\n"
        f"• `/from [источник]` - новости из конкретного СМИ\n\n"
        
        f"**🔍 Tavily Поиск** {search_status}:\n"
        f"• `/search [запрос]` - поиск в интернете\n"
        f"• `/limits` - остаток запросов Tavily\n\n"
        
        f"**🌤 Погода** {weather_status}:\n"
        f"• @{bot_username} какая погода в [город]?\n"
        f"• @{bot_username} сколько градусов в [город]?\n\n"
        
        f"**💬 Как общаться:**\n"
        f"• Упомяните меня `@{bot_username}` с вопросом\n"
        f"• Ответьте (reply) на моё сообщение\n"
        f"• Я помню историю разговоров 🧠\n\n"
        
        f"_Я работаю только в группах, личные сообщения игнорирую_"
    )
    
    await update.message.reply_text(
        help_text,
        reply_to_message_id=update.message.message_id
    )

# ========== RSS НОВОСТИ ==========

async def rss_news_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение новостей через RSS"""
    chat_type = update.effective_chat.type
    if chat_type == "private":
        return
    
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing"
    )
    
    # Если есть аргументы, ищем по запросу
    if context.args:
        query = " ".join(context.args)
        results = await rss_news.search_news(query)
        result = rss_news.format_news_results(results, query)
    else:
        # Без аргументов - свежие новости
        results = await rss_news.get_latest_news(limit=10)
        result = rss_news.format_news_results(results)
    
    await update.message.reply_text(
        result,
        reply_to_message_id=update.message.message_id,
        disable_web_page_preview=True
    )

async def news_from(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Новости из конкретного источника"""
    chat_type = update.effective_chat.type
    if chat_type == "private":
        return
    
    # Формат: /from ria
    if not context.args:
        await update.message.reply_text(
            "❓ Укажите источник новостей.\n\n"
            + rss_news.get_sources_list(),
            reply_to_message_id=update.message.message_id
        )
        return
    
    source = context.args[0].lower()
    
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing"
    )
    
    results = await rss_news.get_latest_news(source=source, limit=5)
    
    if not results:
        await update.message.reply_text(
            f"❌ Источник '{source}' не найден или не содержит новостей.\n\n"
            + rss_news.get_sources_list(),
            reply_to_message_id=update.message.message_id
        )
        return
    
    result = rss_news.format_news_results(results)
    await update.message.reply_text(
        result,
        reply_to_message_id=update.message.message_id,
        disable_web_page_preview=True
    )

async def news_sources(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает список доступных источников новостей"""
    chat_type = update.effective_chat.type
    if chat_type == "private":
        return
    
    sources_list = rss_news.get_sources_list()
    await update.message.reply_text(
        sources_list + "\n\nИспользуйте: `/from источник`",
        reply_to_message_id=update.message.message_id
    )

# ========== КОМАНДЫ TAVILY ПОИСКА ==========

async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Поиск информации через Tavily"""
    chat_type = update.effective_chat.type
    if chat_type == "private":
        return
    
    if not context.args:
        await update.message.reply_text(
            "❓ Укажите запрос для поиска.\n"
            "Пример: `/search последние новости технологий`",
            reply_to_message_id=update.message.message_id
        )
        return
    
    if not TAVILY_API_KEY:
        await update.message.reply_text(
            "😔 Поиск временно недоступен (API ключ не настроен).",
            reply_to_message_id=update.message.message_id
        )
        return
    
    query = " ".join(context.args)
    
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing"
    )
    
    response = await tavily_search.search(query)
    result = tavily_search.format_search_results(response)
    
    await update.message.reply_text(
        result,
        reply_to_message_id=update.message.message_id,
        disable_web_page_preview=True
    )

async def limits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает остаток лимитов Tavily и RSS"""
    chat_type = update.effective_chat.type
    if chat_type == "private":
        return
    
    # Статус Tavily
    tavily_status = tavily_search.get_limits_status() if TAVILY_API_KEY else "🔍 Tavily поиск не настроен"
    
    # RSS безлимитный
    rss_status = "📰 RSS новости: безлимитно (бесплатно)"
    
    message = f"{tavily_status}\n\n{rss_status}"
    
    await update.message.reply_text(
        message,
        reply_to_message_id=update.message.message_id
    )

# ========== ОБРАБОТЧИК КОМАНДЫ START ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    chat_type = update.effective_chat.type
    if chat_type == "private":
        return
    
    bot_username = (await context.bot.get_me()).username
    weather_status = "✅ доступна" if WEATHER_API_KEY else "❌ не настроена"
    search_status = "✅ доступен" if TAVILY_API_KEY else "❌ не настроен"
    
    await update.message.reply_text(
        f"🚀 Привет! Я бот ШМЕЛЬ.\n\n"
        f"**Что я умею:**\n"
        f"• Отвечаю на вопросы (DeepSeek) 🧠\n"
        f"• Запоминаю наши разговоры\n"
        f"• Показываю свежие новости (RSS) 📰\n"
        f"• Ищу в интернете через Tavily 🔍 {search_status}\n"
        f"• Показываю погоду {weather_status}\n\n"
        f"**Команды для новостей:**\n"
        f"• `/news` - свежие новости\n"
        f"• `/news запрос` - поиск новостей\n"
        f"• `/sources` - список источников\n"
        f"• `/from источник` - новости из конкретного СМИ\n\n"
        f"**Другие команды:**\n"
        f"• `/help` - все команды\n"
        f"• `/search запрос` - поиск в интернете\n"
        f"• `/limits` - лимиты\n\n"
        f"**Как общаться:**\n"
        f"• Упомяните меня @{bot_username} с вопросом\n"
        f"• Или просто ответьте на моё сообщение!\n\n"
        f"_Все новости на русском языке, бесплатно и безлимитно!_"
    )

async def show_context(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает текущий контекст чата (для отладки)"""
    chat_type = update.effective_chat.type
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    if chat_type == "private":
        return
    
    user_context = group_context.get_user_context(chat_id, user_id)
    chat_context = group_context.get_chat_context(chat_id, exclude_user_id=user_id)
    
    message = "**📊 Текущий контекст:**\n\n"
    
    if user_context:
        message += f"{user_context}\n\n"
    else:
        message += "📝 История вашего общения: пока пусто\n\n"
    
    if chat_context:
        message += f"{chat_context}\n\n"
    else:
        message += "👥 История чата: пока пусто\n\n"
    
    await update.message.reply_text(
        message,
        reply_to_message_id=update.message.message_id
    )

# ========== ОСНОВНОЙ ОБРАБОТЧИК СООБЩЕНИЙ ==========
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений с поддержкой группового контекста"""
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
    user_name = update.effective_user.first_name or f"User{user_id}"
    
    # ========== ПРОВЕРЯЕМ, НУЖНО ЛИ ОТВЕЧАТЬ ==========
    should_respond = False
    original_message = user_message
    
    # ⭐ ПРОВЕРКА 1: Это ответ на сообщение бота?
    if update.message.reply_to_message:
        reply_to_user = update.message.reply_to_message.from_user
        logger.info(f"📨 Получен reply в чате {chat_id}")
        logger.info(f"   - От кого: {user_name} (ID: {user_id})")
        logger.info(f"   - Кому (оригинал): {reply_to_user.first_name} (ID: {reply_to_user.id})")
        logger.info(f"   - Это бот? {reply_to_user.id == context.bot.id}")
        
        if reply_to_user.id == context.bot.id:
            should_respond = True
            logger.info(f"🔄 Ответ на сообщение бота!")
    
    # ⭐ ПРОВЕРКА 2: Упоминание бота
    if not should_respond and f"@{bot_username}" in user_message:
        should_respond = True
        user_message = user_message.replace(f"@{bot_username}", "").strip()
        logger.info(f"👥 Упоминание бота в группе {chat_id}")
    
    # Всегда сохраняем в контекст
    group_context.add_message(chat_id, user_id, user_name, original_message)
    
    # Если не нужно отвечать - выходим
    if not should_respond:
        return
    
    # Если после удаления упоминания текст пустой
    if not user_message and f"@{bot_username}" in original_message:
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
    
    # Извлекаем факты из сообщения
    await memory.extract_facts_from_message(user_id, original_message)
    
    # Получаем контекст из группы
    context_data = group_context.get_combined_context(
        chat_id, user_id, user_name, original_message
    )
    
    # Получаем личные факты пользователя
    user_facts = await memory.get_user_context(user_id)
    
    # Формируем системный промпт
    system_content = "Ты — полезный ассистент по имени Шмель. Отвечай кратко и по делу."
    
    if context_data["full_context"]:
        system_content += f"\n\n{context_data['full_context']}"
    
    if user_facts:
        system_content += f"\n\n{user_facts}"
    
    if update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id:
        original_bot_message = update.message.reply_to_message.text
        system_content += f"\n\nПользователь отвечает на твое предыдущее сообщение: \"{original_bot_message}\""
    
    logger.info(f"📤 Группа {chat_id}: запрос от {user_name}: {(user_message or original_message)[:50]}...")
    
    try:
        response = await client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_message or original_message},
            ],
            temperature=0.7,
            max_tokens=2000,
        )
        
        bot_reply = response.choices[0].message.content
        logger.info(f"📥 Группа {chat_id}: получен ответ")
        
        group_context.add_message(chat_id, context.bot.id, "Шмель", bot_reply, is_bot_response=True)
        memory.add_to_short_term(user_id, "assistant", bot_reply)
        
        await update.message.reply_text(
            bot_reply,
            reply_to_message_id=update.message.message_id
        )
        logger.info(f"✅ Ответ отправлен в группу {chat_id}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        await update.message.reply_text(
            "😔 Извините, произошла ошибка.",
            reply_to_message_id=update.message.message_id
        )

async def post_init(application: Application):
    """Действия после инициализации бота"""
    await init_memory()
    logger.info("✅ Пост-инициализация завершена")

# ========== ЗАПУСК БОТА ==========

def main():
    """Запуск бота"""
    app = Application.builder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    
    # Регистрируем обработчики команд
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("context", show_context))
    
    # RSS новости
    app.add_handler(CommandHandler("news", rss_news_command))
    app.add_handler(CommandHandler("from", news_from))
    app.add_handler(CommandHandler("sources", news_sources))
    
    # Tavily поиск
    app.add_handler(CommandHandler("search", search))
    app.add_handler(CommandHandler("limits", limits))
    
    # Основной обработчик сообщений
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("🚀 Бот ШМЕЛЬ на базе DeepSeek запущен...")
    logger.info(f"🌤 Погода: {'✅ доступна' if WEATHER_API_KEY else '❌ не настроена'}")
    logger.info(f"🔍 Tavily поиск: {'✅ доступен' if TAVILY_API_KEY else '❌ не настроен'}")
    logger.info("📰 RSS новости: ✅ подключены (бесплатно, безлимитно)")
    logger.info("🧠 Режим: с памятью + групповой контекст")
    logger.info("🔒 Только группы")
    logger.info("💬 Реагирует на: @упоминания и ответы")
    logger.info("📋 Команды: /start, /help, /news, /from, /sources, /search, /limits, /context")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()