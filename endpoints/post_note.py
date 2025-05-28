# endpoints/post_note.py
from flask import Blueprint, request, jsonify
from utils.note_post import NotePoster
import logging
import traceback

logger = logging.getLogger(__name__)
bp = Blueprint('post_note', __name__)

@bp.route('/post_note', methods=['POST'])
def post_note():
    """
    Noteに記事を投稿するエンドポイント
    
    Request Body:
        title (str): 記事のタイトル
        content (str): 記事の本文
        
    Returns:
        JSON: 投稿された記事のURL
    """
    data = request.get_json()
    
    if not data or 'title' not in data or 'content' not in data:
        logger.warning("Missing required fields in request")
        return jsonify({
            'status': 'error',
            'message': 'title and content are required'
        }), 400

    try:
        logger.info(f"Posting article to Note: {data['title']}")
        poster = NotePoster()
        
        # 記事の長さをチェック
        if len(data['content']) > 100000:  # 適切な制限値を設定
            logger.warning("Article content too long")
            return jsonify({
                'status': 'error',
                'message': 'Article content is too long'
            }), 400
            
        note_url = poster.post_article(data['content'], data['title'])
        
        if not note_url:
            logger.error("Failed to post article to Note")
            return jsonify({
                'status': 'error',
                'message': 'Failed to post article',
                'details': 'No URL returned from Note'
            }), 500
            
        logger.info(f"Article posted successfully: {note_url}")
        return jsonify({
            'status': 'success',
            'note_url': note_url
        })
    except Exception as e:
        error_details = {
            'error_type': type(e).__name__,
            'error_message': str(e),
            'traceback': traceback.format_exc()
        }
        logger.error(f"Error posting to Note: {error_details}")
        return jsonify({
            'status': 'error',
            'message': 'Internal server error',
            'details': error_details
        }), 500
