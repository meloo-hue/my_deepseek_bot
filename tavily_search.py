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
    
    async def search(self, query: str, max_results: int = 5, topic: str = "general") -> Dict:
        """
        Выполняет поиск через Tavily
        
        Args:
            query: Поисковый запрос (можно на русском)
            max_results: Максимальное количество результатов (1-20)
            topic: "general" (общий) или "news" (новости)
        
        Returns:
            Dict с результатами поиска
        """
        if not self.client:
            return {"error": "Tavily клиент не инициализирован"}
        
        if not self._check_limits():
            return {"error": "Месячный лимит запросов исчерпан"}
        
        try:
            logger.info(f"🔍 Tavily поиск: {query[:100]}...")
            
            # Параметры поиска с поддержкой русского языка
            response = self.client.search(
                query=query,
                search_depth="advanced",
                topic=topic,
                max_results=max_results,
                include_answer=True,
                include_raw_content=False,
                language="ru"  # 👈 Указываем русский язык
            )
            
            self.monthly_queries += 1
            remaining = self.max_monthly - self.monthly_queries
            
            cost = 2 if response.get('search_depth') == 'advanced' else 1
            logger.info(f"✅ Найдено {len(response.get('results', []))} результатов. "
                       f"Осталось кредитов: {remaining}")
            
            return response
            
        except Exception as e:
            logger.error(f"❌ Ошибка Tavily поиска: {e}")
            return {"error": str(e)}
    
    async def search_news(self, query: str, days: int = 7, max_results: int = 5) -> Dict:
        """
        Поиск новостей через Tavily с поддержкой русского языка
        
        Args:
            query: Поисковый запрос (можно на русском)
            days: За сколько дней искать (до 30)
            max_results: Максимум результатов
        """
        if not self.client:
            return {"error": "Tavily клиент не инициализирован"}
        
        if not self._check_limits():
            return {"error": "Месячный лимит запросов исчерпан"}
        
        try:
            logger.info(f"📰 Tavily поиск новостей: {query[:100]}...")
            
            # Для новостей используем параметры с русским языком
            response = self.client.search(
                query=query,
                search_depth="advanced",
                topic="news",
                max_results=max_results,
                include_answer=False,  # Для новостей ответ не нужен
                include_raw_content=False,
                days=days,
                language="ru"  # 👈 Указываем русский язык
            )
            
            self.monthly_queries += 1
            remaining = self.max_monthly - self.monthly_queries
            
            logger.info(f"✅ Найдено {len(response.get('results', []))} новостей. "
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
        
        if not results and not answer:
            return f"🔍 По запросу '{query}' ничего не найдено."
        
        message = f"🔍 **Результаты поиска по запросу:**\n"
        message += f"_{query}_\n\n"
        
        # Tavily может дать готовый ответ
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
                    content = content[:200] + "..." if len(content) > 200 else content
                    message += f"{content}\n"
                if url:
                    message += f"🔗 [Ссылка]({url})\n"
                message += "\n"
        
        return message.strip()
    
    def format_news_results(self, response: Dict) -> str:
        """Форматирует новости для отправки в чат (на русском)"""
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
                # Преобразуем дату в русский формат если нужно
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
        """Возвращает статус использования лимитов (на русском)"""
        remaining = self.max_monthly - self.monthly_queries
        percent = (self.monthly_queries / self.max_monthly) * 100
        return (f"📊 **Tavily API лимиты:**\n"
                f"• Использовано: {self.monthly_queries}/{self.max_monthly} ({percent:.1f}%)\n"
                f"• Осталось: {remaining} запросов\n"
                f"• Сброс: в начале месяца")


# Глобальный экземпляр
tavily_search = TavilySearchEngine()