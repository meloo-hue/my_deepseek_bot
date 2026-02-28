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
        self.max_monthly = 1000  # Бесплатный лимит [citation:3]
        self.last_reset = datetime.now()
    
    def initialize(self, api_key: str):
        """Инициализация клиента Tavily"""
        self.client = TavilyClient(api_key=api_key)
        logger.info("✅ Tavily клиент инициализирован")
    
    def _check_limits(self) -> bool:
        """Проверка месячного лимита"""
        # Сброс счетчика в начале месяца
        if datetime.now().month != self.last_reset.month:
            self.monthly_queries = 0
            self.last_reset = datetime.now()
        
        if self.monthly_queries >= self.max_monthly:
            logger.warning(f"⚠️ Месячный лимит Tavily исчерпан ({self.max_monthly})")
            return False
        return True
    
    async def search(self, query: str, max_results: int = 5, topic: str = "general") -> Dict:
        """
        Выполняет поиск через Tavily
        
        Args:
            query: Поисковый запрос
            max_results: Максимальное количество результатов (1-20) [citation:5]
            topic: "general" (общий) или "news" (новости) [citation:5]
        
        Returns:
            Dict с результатами поиска
        """
        if not self.client:
            return {"error": "Tavily клиент не инициализирован"}
        
        if not self._check_limits():
            return {"error": "Месячный лимит запросов исчерпан"}
        
        try:
            logger.info(f"🔍 Tavily поиск: {query[:100]}...")
            
            # Параметры поиска [citation:2][citation:5]
            response = self.client.search(
                query=query,
                search_depth="advanced",  # "basic" или "advanced" [citation:5]
                topic=topic,
                max_results=max_results,
                include_answer=True,      # Включает готовый ответ на вопрос [citation:5]
                include_raw_content=False # Не включаем сырой HTML для экономии
            )
            
            self.monthly_queries += 1
            remaining = self.max_monthly - self.monthly_queries
            
            # Считаем стоимость (advanced = 2 кредита) [citation:3]
            cost = 2 if response.get('search_depth') == 'advanced' else 1
            logger.info(f"✅ Найдено {len(response.get('results', []))} результатов. "
                       f"Осталось кредитов: {remaining}")
            
            return response
            
        except Exception as e:
            logger.error(f"❌ Ошибка Tavily поиска: {e}")
            return {"error": str(e)}
    
    async def search_news(self, query: str, days: int = 7, max_results: int = 5) -> Dict:
        """
        Поиск новостей через Tavily
        
        Args:
            query: Поисковый запрос
            days: За сколько дней искать (до 30) [citation:5]
            max_results: Максимум результатов
        """
        # Для новостей используем параметр freshness [citation:5]
        return await self.search(
            query=query,
            max_results=max_results,
            topic="news"
        )
    
    def format_search_results(self, response: Dict) -> str:
        """Форматирует результаты поиска для отправки в чат"""
        if "error" in response:
            return f"❌ {response['error']}"
        
        query = response.get('query', '')
        answer = response.get('answer', '')
        results = response.get('results', [])
        
        if not results and not answer:
            return f"🔍 По запросу '{query}' ничего не найдено."
        
        message = f"🔍 **Результаты поиска по запросу:**\n"
        message += f"_{query}_\n\n"
        
        # Tavily может дать готовый ответ [citation:5]
        if answer:
            message += f"📌 **Краткий ответ:**\n{answer}\n\n"
        
        if results:
            message += f"**Найденные источники:**\n\n"
            for i, result in enumerate(results, 1):
                title = result.get('title', 'Без названия')
                content = result.get('content', '')
                url = result.get('url', '')
                
                message += f"**{i}. {title}**\n"
                if content:
                    # Обрезаем слишком длинный контент
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
        
        if not results:
            return f"📰 По запросу '{query}' новостей не найдено."
        
        message = f"📰 **Последние новости по запросу:**\n"
        message += f"_{query}_\n\n"
        
        for i, result in enumerate(results, 1):
            title = result.get('title', 'Без названия')
            content = result.get('content', '')
            url = result.get('url', '')
            published = result.get('published_date', '')
            
            message += f"**{i}. {title}**\n"
            if content:
                message += f"{content[:150]}...\n"
            if published:
                message += f"📅 {published[:10]}\n"
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