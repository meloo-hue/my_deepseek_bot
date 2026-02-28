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
        self.max_monthly = 1000  # Бесплатный лимит
        self.last_reset = datetime.now()
        
        # Список русскоязычных доменов для приоритизации
        self.russian_domains = [
            "ru", "рф", ".ru", ".рф",
            "yandex.ru", "mail.ru", "rambler.ru",
            "ria.ru", "tass.ru", "interfax.ru",
            "kommersant.ru", "vedomosti.ru", "rbk.ru",
            "gazeta.ru", "lenta.ru", "news.ru",
            "mk.ru", "kp.ru", "aif.ru",
            "fontanka.ru", "dp.ru", "spb.ru",
            "habr.com/ru", "vc.ru", "tjournal.ru"
        ]
        
        # Ключевые слова для определения русского языка
        self.russian_keywords = [
            "россия", "москва", "питер", "спб", "рф",
            "путин", "медведев", "совет", "дума",
            "кремль", "правительство", "министр",
            "рубль", "доллар", "евро", "нефть", "газ"
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
        """Проверяет, является ли результат русскоязычным"""
        title = result.get('title', '').lower()
        content = result.get('content', '').lower()
        url = result.get('url', '').lower()
        
        # Проверка по домену
        for domain in self.russian_domains:
            if domain in url:
                return True
        
        # Проверка по ключевым словам
        text = title + " " + content
        for keyword in self.russian_keywords:
            if keyword in text:
                return True
        
        # Проверка по наличию русских букв
        russian_chars = sum(1 for char in title + content if 'а' <= char <= 'я' or 'А' <= char <= 'Я')
        total_chars = len(title + content)
        if total_chars > 0 and russian_chars / total_chars > 0.3:  # >30% русских букв
            return True
        
        return False
    
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
            
            # Запрашиваем больше результатов для фильтрации
            response = self.client.search(
                query=query,
                search_depth="advanced",
                topic=topic,
                max_results=max_results * 3,  # Запрашиваем больше для фильтрации
                include_answer=True,
                include_raw_content=False
            )
            
            self.monthly_queries += 1
            remaining = self.max_monthly - self.monthly_queries
            
            # Фильтруем результаты, оставляя только русскоязычные
            all_results = response.get('results', [])
            russian_results = []
            
            for result in all_results:
                if self._is_russian_result(result):
                    russian_results.append(result)
                    if len(russian_results) >= max_results:
                        break
            
            # Если не нашли русских результатов, используем первые max_results
            if not russian_results:
                russian_results = all_results[:max_results]
                logger.warning(f"⚠️ Русскоязычных результатов не найдено, использую первые {max_results}")
            
            # Обновляем результаты в ответе
            response['results'] = russian_results
            response['total_found'] = len(all_results)
            response['russian_found'] = len(russian_results)
            
            logger.info(f"✅ Найдено {len(russian_results)} русскоязычных результатов из {len(all_results)}. "
                       f"Осталось кредитов: {remaining}")
            
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
            
            # Запрашиваем больше результатов для фильтрации
            response = self.client.search(
                query=query,
                search_depth="advanced",
                topic="news",
                max_results=max_results * 3,  # Запрашиваем больше для фильтрации
                include_answer=False,
                include_raw_content=False,
                days=days
            )
            
            self.monthly_queries += 1
            remaining = self.max_monthly - self.monthly_queries
            
            # Фильтруем результаты
            all_results = response.get('results', [])
            russian_results = []
            
            for result in all_results:
                if self._is_russian_result(result):
                    russian_results.append(result)
                    if len(russian_results) >= max_results:
                        break
            
            # Если не нашли русских результатов, используем первые max_results
            if not russian_results:
                russian_results = all_results[:max_results]
                logger.warning(f"⚠️ Русскоязычных новостей не найдено, использую первые {max_results}")
            
            response['results'] = russian_results
            response['total_found'] = len(all_results)
            response['russian_found'] = len(russian_results)
            
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
        
        if not results and not answer:
            return f"🔍 По запросу '{query}' ничего не найдено."
        
        message = f"🔍 **Результаты поиска по запросу:**\n"
        message += f"_{query}_\n\n"
        
        # Tavily может дать готовый ответ
        if answer:
            message += f"📌 **Краткий ответ:**\n{answer}\n\n"
        
        if results:
            message += f"**Найденные источники ({russian_found} русскоязычных):**\n\n"
            for i, result in enumerate(results, 1):
                title = result.get('title', 'Без названия')
                content = result.get('content', '')
                url = result.get('url', '')
                
                # Добавляем флаг русскоязычности
                flag = "🇷🇺 " if self._is_russian_result(result) else "🌐 "
                
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
        
        if not results:
            return f"📰 По запросу '{query}' новостей не найдено."
        
        message = f"📰 **Последние новости по запросу:**\n"
        message += f"_{query}_\n\n"
        message += f"**Найдено {russian_found} русскоязычных новостей:**\n\n"
        
        for i, result in enumerate(results, 1):
            title = result.get('title', 'Без названия')
            content = result.get('content', '')
            url = result.get('url', '')
            published = result.get('published_date', '')
            
            # Добавляем флаг русскоязычности
            flag = "🇷🇺 " if self._is_russian_result(result) else "🌐 "
            
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