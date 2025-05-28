# endpoints/generate_article.py
from flask import Blueprint, request, jsonify
from ..utils.gemini_writer import GeminiWriter
from ..utils.logger import get_logger

logger = get_logger(__name__)
bp = Blueprint('generate_article', __name__)

@bp.route('/generate', methods=['POST'])
def generate():
    """
    記事を生成するエンドポイント
    
    Request Body:
        {
            "title": "記事のタイトル",
            "content": "元となるコンテンツ"
        }
    """
    data = request.get_json()
    
    if not data or 'title' not in data or 'content' not in data:
        logger.warning("必要なパラメータが不足しています")
        return jsonify({
            'status': 'error',
            'message': 'title and content are required'
        }), 400
    
    try:
        logger.info(f"Generating article for title: {data['title']}")
        writer = GeminiWriter()
        generated_article = writer.generate_article(data['title'], data['content'])
        logger.info("Article generated successfully")
        
        return jsonify({
            'status': 'success',
            'article': generated_article
        })
    except Exception as e:
        logger.error(f"記事生成中にエラーが発生しました: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500
