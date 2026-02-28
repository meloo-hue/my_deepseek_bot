import os
import logging
from typing import List, Dict, Optional
from datetime import datetime
from tavily import TavilyClient

logger = logging.getLogger(__name__)

class TavilySearchEngine:
    """Поисковый движок на базе Tavily API"""
    
    def __init__(self):
        self.client = None
        self.monthly_queries = 0
        self.max_monthly = 1000
        self.last_reset = datetime.now()
        
        # Белый список русскоязычных доменов
        self.russian_domains = [
            # Новостные агентства
            "ria.ru", "tass.ru", "interfax.ru", "rbc.ru", "kommersant.ru",
            "vedomosti.ru", "gazeta.ru", "lenta.ru", "news.ru", "mk.ru",
            "kp.ru", "aif.ru", "fontanka.ru", "dp.ru", "spb.ru",
            "echo.msk.ru", "svoboda.org", "currenttime.tv",
            "meduza.io", "novayagazeta.eu", "istories.media",
            "the-village.ru", "paperpaper.ru", "bumaga.ru",
            
            # Поисковики и порталы
            "yandex.ru", "mail.ru", "rambler.ru", "ya.ru",
            
            # IT и технологии
            "habr.com", "habr.ru", "vc.ru", "tjournal.ru", "dtf.ru",
            "ixbt.com", "overclockers.ru", "3dnews.ru",
            
            # Спорт
            "sports.ru", "championat.com", "sovsport.ru",
            
            # Региональные
            "msk.ru", "spb.ru", "nn.ru", "eka.ru", "ufa.ru"
        ]
        
        # Слова для определения русского языка
        self.russian_words = [
            "что", "как", "так", "все", "это", "они", "мы", "вы", "ты",
            "россия", "москва", "питер", "спб", "российской", "российский",
            "президент", "путин", "правительство", "госдума", "совет",
            "рубль", "доллар", "евро", "нефть", "газ", "бензин",
            "новости", "события", "происшествия", "политика", "экономика",
            "спорт", "культура", "технологии", "наука", "образование",
            "сегодня", "вчера", "завтра", "сейчас", "после", "потом",
            "год", "месяц", "день", "неделя", "часы", "минуты",
            "человек", "люди", "город", "страна", "мир", "регион"
        ]
    
    def initialize(self, api_key: str):
        """Инициализация клиента Tavily"""
        self.client = TavilyClient(api_key=api_key)
        logger.info("✅ Tavily клиент инициализирован")
    
    def _check_limits(self) -> bool:
        """Проверка месячного лимита"""
        if datetime.now().month != self.last_reset.month:
            self.monthly_queries = 0
            self.last_reset = datetime.now()
        
        if self.monthly_queries >= self.max_monthly:
            logger.warning(f"⚠️ Месячный лимит Tavily исчерпан ({self.max_monthly})")
            return False
        return True
    
    def _is_russian_result(self, result: Dict) -> bool:
        """Улучшенная проверка русскоязычности результата"""
        title = result.get('title', '')
        content = result.get('content', '')
        url = result.get('url', '').lower()
        
        # 1. Проверка по домену (самый надежный способ)
        for domain in self.russian_domains:
            if domain in url:
                logger.debug(f"✅ Русский домен: {domain} в {url}")
                return True
        
        # 2. Проверка по наличию русских букв в тексте
        text = (title + " " + content)[:1000]  # Первые 1000 символов
        
        # Считаем русские и английские буквы
        russian_count = 0
        english_count = 0
        total_chars = 0
        
        for char in text:
            if 'а' <= char.lower() <= 'я' or char.lower() in ['ё', 'ъ', 'ы', 'э']:
                russian_count += 1
            elif 'a' <= char.lower() <= 'z':
                english_count += 1
            total_chars += 1
        
        # Если текст слишком короткий, не можем определить
        if total_chars < 20:
            return False
        
        # Вычисляем процент русских букв
        russian_percent = russian_count / (russian_count + english_count + 1) * 100
        
        # 3. Проверка по словам
        text_lower = text.lower()
        russian_word_count = 0
        for word in self.russian_words:
            if word in text_lower:
                russian_word_count += 1
        
        # Принимаем решение
        is_russian = (
            russian_percent > 50 or  # Больше 50% русских букв
            russian_word_count > 3    # Или найдено больше 3 русских слов
        )
        
        if is_russian:
            logger.debug(f"✅ Русский текст: {russian_percent:.1f}% русских букв, {russian_word_count} русских слов")
        else:
            logger.debug(f"❌ Не русский текст: {russian_percent:.1f}% русских букв, {russian_word_count} русских слов")
        
        return is_russian
    
    async def search(self, query: str, max_results: int = 5, topic: str = "general") -> Dict:
        """
        Выполняет поиск через Tavily с приоритетом русскоязычных результатов
        """
        if not self.client:
            return {"error": "Tavily клиент не инициализирован"}
        
        if not self._check_limits():
            return {"error": "Месячный лимит запросов исчерпан"}
        
        try:
            logger.info(f"🔍 Tavily поиск: {query[:100]}...")
            
            # Добавляем в запрос указание на русский язык
            enhanced_query = f"{query} -английский -english"
            
            response = self.client.search(
                query=enhanced_query,
                search_depth="advanced",
                topic=topic,
                max_results=max_results * 5,  # Запрашиваем больше для фильтрации
                include_answer=True,
                include_raw_content=False
            )
            
            self.monthly_queries += 1
            remaining = self.max_monthly - self.monthly_queries
            
            # Фильтруем результаты
            all_results = response.get('results', [])
            russian_results = []
            other_results = []
            
            for result in all_results:
                if self._is_russian_result(result):
                    russian_results.append(result)
                else:
                    other_results.append(result)
            
            # Берем русские результаты, если есть, иначе английские
            if len(russian_results) >= max_results:
                final_results = russian_results[:max_results]
                used_russian = True
            elif russian_results:
                final_results = russian_results + other_results[:max_results - len(russian_results)]
                used_russian = True
            else:
                final_results = other_results[:max_results]
                used_russian = False
            
            response['results'] = final_results
            response['total_found'] = len(all_results)
            response['russian_found'] = len(russian_results)
            response['used_russian'] = used_russian
            
            logger.info(f"✅ Найдено {len(russian_results)} русскоязычных из {len(all_results)}. "
                       f"Использовано: {len(final_results)}. Осталось кредитов: {remaining}")
            
            return response
            
        except Exception as e:
            logger.error(f"❌ Ошибка Tavily поиска: {e}")
            return {"error": str(e)}
    
    async def search_news(self, query: str, days: int = 7, max_results: int = 5) -> Dict:
        """
        Поиск новостей через Tavily с приоритетом русскоязычных источников
        """
        if not self.client:
            return {"error": "Tavily клиент не инициализирован"}
        
        if not self._check_limits():
            return {"error": "Месячный лимит запросов исчерпан"}
        
        try:
            logger.info(f"📰 Tavily поиск новостей: {query[:100]}...")
            
            # Добавляем в запрос указание на русский язык
            enhanced_query = f"{query} -английский -english -uk -us -gb"
            
            response = self.client.search(
                query=enhanced_query,
                search_depth="advanced",
                topic="news",
                max_results=max_results * 5,
                include_answer=False,
                include_raw_content=False,
                days=days
            )
            
            self.monthly_queries += 1
            remaining = self.max_monthly - self.monthly_queries
            
            # Фильтруем результаты
            all_results = response.get('results', [])
            russian_results = []
            other_results = []
            
            for result in all_results:
                if self._is_russian_result(result):
                    russian_results.append(result)
                else:
                    other_results.append(result)
            
            # Берем русские результаты, если есть
            if len(russian_results) >= max_results:
                final_results = russian_results[:max_results]
                used_russian = True
            elif russian_results:
                final_results = russian_results + other_results[:max_results - len(russian_results)]
                used_russian = True
            else:
                final_results = other_results[:max_results]
                used_russian = False
            
            response['results'] = final_results
            response['total_found'] = len(all_results)
            response['russian_found'] = len(russian_results)
            response['used_russian'] = used_russian
            
            logger.info(f"✅ Найдено {len(russian_results)} русскоязычных новостей из {len(all_results)}. "
                       f"Осталось кредитов: {remaining}")
            
            return response
            
        except Exception as e:
            logger.error(f"❌ Ошибка Tavily поиска новостей: {e}")
            return {"error": str(e)}
    
    def format_search_results(self, response: Dict) -> str:
        """Форматирует результаты поиска для отправки в чат"""
        if "error" in response:
            return f"❌ {response['error']}"
        
        query = response.get('query', '')
        answer = response.get('answer', '')
        results = response.get('results', [])
        russian_found = response.get('russian_found', 0)
        used_russian = response.get('used_russian', False)
        
        if not results and not answer:
            return f"🔍 По запросу '{query}' ничего не найдено."
        
        message = f"🔍 **Результаты поиска по запросу:**\n"
        message += f"_{query}_\n\n"
        
        if not used_russian:
            message += "⚠️ **Внимание:** Не найдено русскоязычных источников, показываю английские.\n\n"
        
        if answer and used_russian:
            message += f"📌 **Краткий ответ:**\n{answer}\n\n"
        
        if results:
            for i, result in enumerate(results, 1):
                title = result.get('title', 'Без названия')
                content = result.get('content', '')
                url = result.get('url', '')
                
                # Проверяем язык этого конкретного результата
                is_russian = self._is_russian_result(result)
                flag = "🇷🇺 " if is_russian else "🇬🇧 "
                
                message += f"**{i}. {flag}{title}**\n"
                if content:
                    content = content[:200] + "..." if len(content) > 200 else content
                    message += f"{content}\n"
                if url:
                    message += f"🔗 [Ссылка]({url})\n"
                message += "\n"
        
        return message.strip()
    
    def format_news_results(self, response: Dict) -> str:
        """Форматирует новости для отправки в чат"""
        if "error" in response:
            return f"❌ {response['error']}"
        
        query = response.get('query', '')
        results = response.get('results', [])
        russian_found = response.get('russian_found', 0)
        used_russian = response.get('used_russian', False)
        
        if not results:
            return f"📰 По запросу '{query}' новостей не найдено."
        
        message = f"📰 **Последние новости по запросу:**\n"
        message += f"_{query}_\n\n"
        
        if not used_russian:
            message += "⚠️ **Внимание:** Не найдено русскоязычных новостей, показываю английские.\n\n"
        else:
            message += f"**Найдено {russian_found} русскоязычных новостей:**\n\n"
        
        for i, result in enumerate(results, 1):
            title = result.get('title', 'Без названия')
            content = result.get('content', '')
            url = result.get('url', '')
            published = result.get('published_date', '')
            
            # Проверяем язык этого конкретного результата
            is_russian = self._is_russian_result(result)
            flag = "🇷🇺 " if is_russian else "🇬🇧 "
            
            message += f"**{i}. {flag}{title}**\n"
            if content:
                message += f"{content[:150]}...\n"
            if published:
                try:
                    pub_date = datetime.fromisoformat(published.replace('Z', '+00:00'))
                    published = pub_date.strftime("%d.%m.%Y %H:%M")
                except:
                    published = published[:10]
                message += f"📅 {published}\n"
            if url:
                message += f"🔗 [Читать]({url})\n"
            message += "\n"
        
        return message.strip()
    
    def get_limits_status(self) -> str:
        """Возвращает статус использования лимитов"""
        remaining = self.max_monthly - self.monthly_queries
        percent = (self.monthly_queries / self.max_monthly) * 100
        return (f"📊 **Tavily API лимиты:**\n"
                f"• Использовано: {self.monthly_queries}/{self.max_monthly} ({percent:.1f}%)\n"
                f"• Осталось: {remaining} запросов\n"
                f"• Сброс: в начале месяца")


# Глобальный экземпляр
tavily_search = TavilySearchEngine()