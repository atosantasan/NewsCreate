# endpoints/generate_article.py
from flask import Blueprint, request, jsonify
from utils.gemini_writer import GeminiWriter
import logging

logger = logging.getLogger(__name__)
bp = Blueprint('generate_article', __name__)

@bp.route('/generate', methods=['POST'])
def generate():
    """
    ニュース情報から記事を生成するエンドポイント
    
    Request Body:
        title (str): ニュースのタイトル
        content (str): ニュースの本文
        
    Returns:
        JSON: 生成された記事本文
    """
    data = request.get_json()
    
    if not data or 'title' not in data or 'content' not in data:
        logger.warning("Missing required fields in request")
        return jsonify({
            'status': 'error',
            'message': 'title and content are required'
        }), 400
    
    try:
        logger.info(f"Generating article for title: {data['title']}")
        writer = GeminiWriter()
        article = writer.generate_article(data['title'], data['content'])
        logger.info("Article generated successfully")
        
        return jsonify({
            'status': 'success',
            'article': article
        })
    except Exception as e:
        logger.error(f"Error generating article: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500
