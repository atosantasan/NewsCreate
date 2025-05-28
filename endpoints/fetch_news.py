# endpoints/fetch_news.py
from flask import Blueprint, jsonify
from ..utils.news_fetcher import NewsFetcher
import logging

logger = logging.getLogger(__name__)
bp = Blueprint('fetch_news', __name__)

@bp.route('/fetch_news', methods=['GET'])
def fetch_news():
    """
    RSSフィードからニュース記事を取得するエンドポイント
    
    Returns:
        JSON: 取得したニュース記事のリスト
    """
    try:
        logger.info("Fetching news articles")
        fetcher = NewsFetcher()
        articles = fetcher.fetch_news()
        logger.info(f"Successfully fetched {len(articles)} articles")
        return jsonify({
            'status': 'success',
            'articles': articles
        })
    except Exception as e:
        logger.error(f"Error fetching news: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500
