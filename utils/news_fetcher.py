import feedparser
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import os
from dotenv import load_dotenv
import requests
from bs4 import BeautifulSoup
import time

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

    def _fetch_article_content(self, url: str) -> str:
        """
        記事のURLからコンテンツを取得する

        Args:
            url (str): 記事のURL

        Returns:
            str: 記事のコンテンツ
        """
        try:
            # ユーザーエージェントを設定してブロックを回避
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            logger.info(f"Fetching content from URL: {url}")
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            # HTMLをパース
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 不要な要素を削除
            for tag in soup(['script', 'style', 'nav', 'header', 'footer', 'aside', 'iframe', 'form', 'button']):
                tag.decompose()
            
            # メインコンテンツを取得（サイトによって異なる可能性がある）
            content = None
            content_selectors = [
                'article',
                'main',
                'div.content',
                'div.article',
                'div.post',
                'div.entry-content',
                'div.story-body',
                'div.article-body',
                'div.article-content',
                'div.post-content',
                'div.entry',
                'div.post-body',
                'div.article-text',
                'div.article-main',
                'div.article-detail',
                'div.article-body-text',
                'div.article-body-content',
                'div.article-body-main',
                'div.article-body-detail',
                'div.article-body-text-content',
                'div.article-body-text-main',
                'div.article-body-text-detail',
                'div.article-body-text-content-main',
                'div.article-body-text-content-detail',
                'div.article-body-text-main-detail',
                'div.article-body-text-content-main-detail',
                'div.article-body-text-content-main-detail-content',
                'div.article-body-text-content-main-detail-text',
                'div.article-body-text-content-main-detail-main',
                'div.article-body-text-content-main-detail-detail',
                'div.article-body-text-content-main-detail-content-text',
                'div.article-body-text-content-main-detail-content-main',
                'div.article-body-text-content-main-detail-content-detail',
                'div.article-body-text-content-main-detail-text-main',
                'div.article-body-text-content-main-detail-text-detail',
                'div.article-body-text-content-main-detail-main-detail',
                'div.article-body-text-content-main-detail-content-text-main',
                'div.article-body-text-content-main-detail-content-text-detail',
                'div.article-body-text-content-main-detail-content-main-detail',
                'div.article-body-text-content-main-detail-text-main-detail',
                'div.article-body-text-content-main-detail-content-text-main-detail'
            ]
            
            for selector in content_selectors:
                content = soup.select_one(selector)
                if content:
                    logger.info(f"Found content using selector: {selector}")
                    break
            
            if content:
                # テキストを取得して整形
                text = content.get_text(separator='\n', strip=True)
                if text:
                    logger.info(f"Successfully extracted content from {url}")
                    return text
                else:
                    logger.warning(f"Found content element but it was empty for {url}")
            else:
                logger.warning(f"Could not find main content element for {url}")
                # メインコンテンツが見つからない場合はbody全体を使用
                if soup.body:
                    text = soup.body.get_text(separator='\n', strip=True)
                    if text:
                        logger.info(f"Using body content as fallback for {url}")
                        return text
                    else:
                        logger.warning(f"Body content was empty for {url}")
                else:
                    logger.warning(f"No body element found for {url}")
            
            return ""
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error fetching article content from {url}: {str(e)}")
            return ""
        except Exception as e:
            logger.error(f"Unexpected error fetching article content from {url}: {str(e)}")
            return ""

    def fetch_news(self, max_articles: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        RSSフィードからニュース記事を取得する。
        取得する記事の最大件数を指定できる。

        Args:
            max_articles (Optional[int]): 取得する記事の最大件数。Noneの場合は全ての記事を取得。

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
                        # 記事のURLからコンテンツを取得
                        article_url = entry.link
                        article_content = self._fetch_article_content(article_url)
                        
                        # コンテンツが空の場合はsummaryを使用
                        if not article_content and 'summary' in entry:
                            logger.info(f"Using RSS summary as fallback for {article_url}")
                            article_content = entry.summary
                        
                        article = {
                            "title": entry.title,
                            "content": article_content,
                            "url": article_url,
                            "published": entry.get("published", datetime.now().isoformat()),
                            "source": url
                        }
                        articles.append(article)
                        
                        # サーバーに負荷をかけないように少し待機
                        time.sleep(1)
                        
                        # 取得件数が最大件数に達したらループを抜ける
                        if max_articles is not None and len(articles) >= max_articles:
                            logger.info(f"Reached maximum number of articles ({max_articles}). Stopping fetch.")
                            break # entry ループを抜ける

                    except Exception as e:
                        logger.error(f"Error processing entry from {url}: {str(e)}")
                        continue
                        
            except Exception as e:
                logger.error(f"Error fetching feed from {url}: {str(e)}")
                continue
                
            # 取得件数が最大件数に達したら外側のフィードループも抜ける
            if max_articles is not None and len(articles) >= max_articles:
                break # url ループを抜ける
                
        logger.info(f"Successfully fetched {len(articles)} articles")
        return articles
