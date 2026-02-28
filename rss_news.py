import feedparser
import aiohttp
import asyncio
import logging
from typing import List, Dict, Optional
from datetime import datetime
import html
import re

logger = logging.getLogger(__name__)

class RSSNewsEngine:
    """Поисковый движок на базе RSS-лент российских СМИ"""
    
    def __init__(self):
        self.sources = {
            # Главные новостные агентства
            "ria": {
                "url": "https://ria.ru/export/rss2/index.xml",
                "name": "РИА Новости"
            },
            "tass": {
                "url": "http://tass.ru/rss/v2.xml",
                "name": "ТАСС"
            },
            "interfax": {
                "url": "https://www.interfax.ru/rss.asp",
                "name": "Интерфакс"
            },
            "rbc": {
                "url": "https://rssexport.rbc.ru/rbc/news/20/full.rss",
                "name": "РБК"
            },
            
            # Газеты
            "rg": {
                "url": "https://rg.ru/xml/index.xml",
                "name": "Российская Газета"
            },
            "kp": {
                "url": "https://www.kp.ru/rss/alls.xml",
                "name": "Комсомольская Правда"
            },
            "mk": {
                "url": "https://www.mk.ru/rss/news/index.xml",
                "name": "Московский Комсомолец"
            },
            "iz": {
                "url": "https://iz.ru/xml/rss/all.xml",
                "name": "Известия"
            },
            "aif": {
                "url": "https://aif.ru/rss/all.php",
                "name": "Аргументы и Факты"
            },
            "kommersant": {
                "url": "https://www.kommersant.ru/RSS/news.xml",
                "name": "Коммерсантъ"
            },
            "vedomosti": {
                "url": "https://vedomosti.ru/rss/news",
                "name": "Ведомости"
            },
            
            # Онлайн-издания
            "lenta": {
                "url": "https://lenta.ru/rss/news",
                "name": "Lenta.ru"
            },
            "gazeta": {
                "url": "https://www.gazeta.ru/export/rss/full.xml",
                "name": "Gazeta.ru"
            },
            "life": {
                "url": "https://life.ru/life.rss",
                "name": "Life.ru"
            },
            
            # Региональные
            "fontanka": {
                "url": "https://www.fontanka.ru/fontanka.rss",
                "name": "Фонтанка.ру"
            },
            "dp": {
                "url": "https://www.dp.ru/export/export-dp-rss.xml",
                "name": "Деловой Петербург"
            }
        }
        
        self.queries_today = 0
        self.max_daily = 1000  # Условный лимит, на самом деле безлимитно
        self.last_reset = datetime.now().date()
    
    def _check_limits(self) -> bool:
        """Проверка дневного лимита (для совместимости)"""
        today = datetime.now().date()
        if today != self.last_reset:
            self.queries_today = 0
            self.last_reset = today
        
        if self.queries_today >= self.max_daily:
            logger.warning(f"⚠️ Дневной лимит RSS ({self.max_daily})")
            return False
        return True
    
    def _parse_date(self, published: str) -> str:
        """Преобразует дату из RSS в читаемый формат"""
        if not published:
            return ""
        
        try:
            # Пробуем разные форматы дат
            if 'T' in published:  # ISO формат
                pub_date = datetime.fromisoformat(published.replace('Z', '+00:00'))
                return pub_date.strftime("%d.%m.%Y %H:%M")
            elif 'GMT' in published:
                pub_date = datetime.strptime(published, "%a, %d %b %Y %H:%M:%S GMT")
                return pub_date.strftime("%d.%m.%Y %H:%M")
            else:
                # Просто обрезаем до первых 16 символов
                return published[:16]
        except:
            return published[:10]
    
    async def get_latest_news(self, source: str = "all", limit: int = 5) -> List[Dict]:
        """
        Получает последние новости из указанных источников
        
        Args:
            source: "all" или ключ источника (например, "ria")
            limit: Сколько новостей получить
        """
        if not self._check_limits():
            return []
        
        results = []
        
        # Определяем, какие источники использовать
        if source == "all":
            sources_to_check = list(self.sources.items())
        else:
            sources_to_check = [(source, self.sources.get(source, {}))]
        
        for src_key, src_info in sources_to_check:
            if not src_info:
                continue
                
            try:
                logger.info(f"📡 Читаю RSS: {src_info['name']}")
                
                # Парсим RSS (feedparser синхронный, запускаем в потоке)
                loop = asyncio.get_event_loop()
                feed = await loop.run_in_executor(
                    None, 
                    lambda: feedparser.parse(src_info['url'])
                )
                
                if not feed.entries:
                    logger.warning(f"⚠️ Пустой RSS: {src_info['name']}")
                    continue
                
                for entry in feed.entries[:3]:  # Берем по 3 из каждого источника
                    # Очищаем HTML из заголовка
                    title = html.unescape(entry.get('title', 'Без названия'))
                    title = re.sub('<[^<]+?>', '', title)
                    
                    # Ссылка на новость
                    link = entry.get('link', '')
                    
                    # Краткое описание
                    summary = html.unescape(entry.get('summary', ''))
                    summary = re.sub('<[^<]+?>', '', summary)[:200]
                    
                    # Дата публикации
                    published = entry.get('published', '')
                    date = self._parse_date(published)
                    
                    results.append({
                        "title": title,
                        "content": summary,
                        "url": link,
                        "date": date,
                        "source": src_info['name'],
                        "source_key": src_key,
                        "is_russian": True
                    })
                    
            except Exception as e:
                logger.error(f"❌ Ошибка RSS {src_info.get('name', src_key)}: {e}")
                continue
        
        # Сортируем по дате (свежие сверху)
        results.sort(key=lambda x: x['date'], reverse=True)
        
        self.queries_today += 1
        logger.info(f"✅ RSS: собрано {len(results)} новостей")
        
        return results[:limit]
    
    async def search_news(self, query: str, limit: int = 5) -> List[Dict]:
        """
        Ищет новости по ключевым словам
        
        Args:
            query: Поисковый запрос
            limit: Сколько результатов вернуть
        """
        # Получаем свежие новости
        all_news = await self.get_latest_news(limit=50)
        
        # Фильтруем по запросу
        query_lower = query.lower()
        filtered = []
        
        for news in all_news:
            title_lower = news['title'].lower()
            content_lower = news['content'].lower()
            
            if (query_lower in title_lower or 
                query_lower in content_lower):
                filtered.append(news)
            
            if len(filtered) >= limit:
                break
        
        return filtered[:limit]
    
    def format_news_results(self, results: List[Dict], query: str = "") -> str:
        """Форматирует новости для отправки в чат"""
        if not results:
            return "📰 Новостей не найдено."
        
        if query:
            message = f"📰 **Новости по запросу:**\n"
            message += f"_{query}_\n\n"
        else:
            message = f"📰 **Свежие новости:**\n\n"
        
        for i, item in enumerate(results, 1):
            title = item.get('title', 'Без названия')
            source = item.get('source', 'Новости')
            date = item.get('date', '')
            url = item.get('url', '')
            
            message += f"**{i}. 🇷🇺 {title}**\n"
            message += f"📰 {source}"
            if date:
                message += f" 📅 {date}"
            message += "\n"
            
            if item.get('content'):
                message += f"_{item['content']}_\n"
            
            if url:
                message += f"🔗 [Читать]({url})\n"
            message += "\n"
        
        return message.strip()
    
    def get_sources_list(self) -> str:
        """Возвращает список доступных источников"""
        sources = []
        for key, info in self.sources.items():
            sources.append(f"• {info['name']} (/{key})")
        
        return "📰 **Доступные источники:**\n" + "\n".join(sources)


# Глобальный экземпляр
rss_news = RSSNewsEngine()