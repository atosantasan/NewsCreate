import feedparser
import logging
from typing import List, Dict, Any
from datetime import datetime
import os
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

class NewsFetcher:
    def __init__(self):
        load_dotenv()
        self.rss_feeds = os.getenv('RSS_FEED_URLS', '').split(',')
        if not self.rss_feeds or self.rss_feeds[0] == '':
            self.rss_feeds = [
                "https://news.google.com/rss/search?q=AI&hl=ja&gl=JP&ceid=JP:ja",
                "https://gigazine.net/news/rss_2.0/",
            ]
            logger.warning("Using default RSS feeds as no feeds were configured in environment variables")

    def fetch_news(self) -> List[Dict[str, Any]]:
        """
        RSSフィードからニュース記事を取得する
        
        Returns:
            List[Dict[str, Any]]: 取得したニュース記事のリスト
        """
        articles = []
        
        for url in self.rss_feeds:
            try:
                logger.info(f"Fetching news from: {url}")
                feed = feedparser.parse(url)
                
                if feed.bozo:  # RSSフィードのパースエラーをチェック
                    logger.warning(f"Feed parsing error for {url}: {feed.bozo_exception}")
                    continue
                
                for entry in feed.entries:
                    try:
                        article = {
                            "title": entry.title,
                            "content": entry.get("summary", ""),
                            "url": entry.link,
                            "published": entry.get("published", datetime.now().isoformat()),
                            "source": url
                        }
                        articles.append(article)
                    except Exception as e:
                        logger.error(f"Error processing entry from {url}: {str(e)}")
                        continue
                        
            except Exception as e:
                logger.error(f"Error fetching feed from {url}: {str(e)}")
                continue
                
        logger.info(f"Successfully fetched {len(articles)} articles")
        return articles
