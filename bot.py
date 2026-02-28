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

# ========== ОБРАБОТЧИКИ ==========

async def init_memory():
    await memory.init_db()
    logger.info("🧠 Память инициализирована")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_type = update.effective_chat.type
    if chat_type == "private":
        return
    
    bot_username = (await context.bot.get_me()).username
    weather_status = "✅ доступна" if WEATHER_API_KEY else "❌ не настроена"
    
    await update.message.reply_text(
        f"🚀 Привет! Я бот ШМЕЛЬ.\n\n"
        f"**Что я умею:**\n"
        f"• Отвечаю на вопросы (DeepSeek)\n"
        f"• Запоминаю наши разговоры 🧠\n"
        f"• Показываю погоду {weather_status}\n\n"
        f"**Как спросить погоду:**\n"
        f"• @{bot_username} какая погода в Москве?\n"
        f"• @{bot_username} сколько градусов в Лондоне?\n\n"
        f"**Как использовать:**\n"
        f"Упомяните меня @{bot_username} с вопросом"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Умный обработчик с Function Calling"""
    chat_type = update.effective_chat.type
    
    if chat_type == "private":
        return
    
    if chat_type not in ["group", "supergroup"]:
        return
    
    user_message = update.message.text
    bot_username = (await context.bot.get_me()).username
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    # Проверяем упоминание
    if f"@{bot_username}" not in user_message:
        return
    
    user_message = user_message.replace(f"@{bot_username}", "").strip()
    
    if not user_message:
        await update.message.reply_text(
            "❓ Напишите вопрос после упоминания",
            reply_to_message_id=update.message.message_id
        )
        return
    
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    
    # Извлекаем факты
    await memory.extract_facts_from_message(user_id, user_message)
    
    # Получаем контекст из памяти
    short_context = memory.get_conversation_context(user_id)
    user_context = await memory.get_user_context(user_id)
    
    memory.add_to_short_term(user_id, "user", user_message)
    
    logger.info(f"📤 Запрос от {user_id}: {user_message[:100]}...")
    
    try:
        # Формируем системный промпт
        system_content = "Ты — полезный ассистент по имени Шмель."
        if user_context:
            system_content += f"\n\n{user_context}"
        if short_context:
            system_content += f"\n\n{short_context}"
        
        # Первый запрос к DeepSeek (может вернуть вызов функции)
        response = await client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_message}
            ],
            tools=[weather_tool] if WEATHER_API_KEY else None,
            tool_choice="auto" if WEATHER_API_KEY else None,
            temperature=0.7,
            max_tokens=2000,
        )
        
        message = response.choices[0].message
        
        # Проверяем, вызвал ли DeepSeek функцию
        if message.tool_calls:
            # Вызываем реальную функцию погоды
            for tool_call in message.tool_calls:
                if tool_call.function.name == "get_weather":
                    args = json.loads(tool_call.function.arguments)
                    city = args.get("city")
                    
                    logger.info(f"🌤 Запрос погоды для города: {city}")
                    
                    # Реальный запрос к API
                    weather_result = await get_weather_from_api(city)
                    
                    # Отправляем результат обратно в DeepSeek
                    response2 = await client.chat.completions.create(
                        model=MODEL_NAME,
                        messages=[
                            {"role": "system", "content": system_content},
                            {"role": "user", "content": user_message},
                            message,
                            {
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": weather_result
                            }
                        ],
                        temperature=0.7,
                        max_tokens=2000,
                    )
                    
                    bot_reply = response2.choices[0].message.content
                else:
                    bot_reply = "Извините, я не могу выполнить эту функцию."
        else:
            # Обычный ответ без вызова функции
            bot_reply = message.content
        
        logger.info(f"📥 Получен ответ")
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

async def post_init(app):
    await init_memory()

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("🚀 Бот ШМЕЛЬ на базе DeepSeek запущен...")
    logger.info(f"🌤 Погода: {'✅ доступна' if WEATHER_API_KEY else '❌ не настроена'}")
    logger.info("🧠 Режим: с памятью + Function Calling")
    logger.info("🔒 Только группы")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()