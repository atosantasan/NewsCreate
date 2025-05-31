# endpoints/fetch_news.py
from flask import Blueprint, jsonify, request
from utils.news_fetcher import NewsFetcher
import logging

logger = logging.getLogger(__name__)
bp = Blueprint('fetch_news', __name__)

@bp.route('/fetch_news', methods=['GET'])
def fetch_news():
    """
    RSSフィードからニュース記事を取得するエンドポイント
    取得する記事の最大件数を`max_articles`クエリパラメータで指定可能。

    Args:
        max_articles (int, optional): 取得する記事の最大件数。指定しない場合は全て取得。
    
    Returns:
        JSON: 取得したニュース記事のリスト
    """
    max_articles = request.args.get('max_articles', type=int)

    try:
        logger.info(f"Fetching news articles (max_articles: {max_articles if max_articles is not None else 'None'}) ")
        fetcher = NewsFetcher()
        articles = fetcher.fetch_news(max_articles=max_articles)
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
