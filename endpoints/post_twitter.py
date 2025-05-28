# endpoints/post_twitter.py
from flask import Blueprint, request, jsonify
from ..utils.twitter_bot import TwitterBot
import logging

logger = logging.getLogger(__name__)
bp = Blueprint('post_twitter', __name__)

@bp.route('/post_twitter', methods=['POST'])
def post_twitter():
    """
    Twitterにツイートを投稿するエンドポイント
    
    Request Body:
        title (str): ツイートのタイトル
        url (str): ツイートに含めるURL
        
    Returns:
        JSON: 投稿結果
    """
    data = request.get_json()
    
    if not data or 'title' not in data or 'url' not in data:
        logger.warning("Missing required fields in request")
        return jsonify({
            'status': 'error',
            'message': 'title and url are required'
        }), 400

    try:
        logger.info(f"Posting tweet: {data['title']}")
        bot = TwitterBot()
        success = bot.post_tweet(data['title'], data['url'])
        
        if not success:
            logger.error("Failed to post tweet")
            return jsonify({
                'status': 'error',
                'message': 'Failed to post tweet'
            }), 500
            
        logger.info("Tweet posted successfully")
        return jsonify({
            'status': 'success',
            'message': 'Tweet posted successfully'
        })
    except Exception as e:
        logger.error(f"Error posting to Twitter: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500
