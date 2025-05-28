from flask import Flask, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_cors import CORS
from .config import config
from .utils.logger import setup_logger
import logging

logger = logging.getLogger(__name__)

def create_app(config_name='default'):
    app = Flask(__name__)
    
    # 設定の読み込み
    app.config.from_object(config[config_name])
    
    # CORSの設定
    CORS(app, resources={
        r"/api/*": {
            "origins": app.config.get('CORS_ORIGINS', []),
            "methods": ["GET", "POST", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"],
            "expose_headers": ["Content-Range", "X-Content-Range"],
            "supports_credentials": True,
            "max_age": 600
        }
    })
    
    # セキュリティヘッダーの設定
    @app.after_request
    def add_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        response.headers['Content-Security-Policy'] = "default-src 'self'"
        return response
    
    # レート制限の設定
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=["200 per day", "50 per hour"],
        storage_uri=app.config.get('RATELIMIT_STORAGE_URL', 'memory://')
    )
    
    # ロギングの設定
    setup_logger(app)
    
    # エンドポイントの登録
    from .endpoints import fetch_news, generate_article, post_note, post_twitter
    app.register_blueprint(fetch_news.bp, url_prefix='/api/v1')
    app.register_blueprint(generate_article.bp, url_prefix='/api/v1')
    app.register_blueprint(post_note.bp, url_prefix='/api/v1')
    app.register_blueprint(post_twitter.bp, url_prefix='/api/v1')
    
    # グローバルエラーハンドラー
    @app.errorhandler(400)
    def bad_request(error):
        logger.error(f"Bad request: {str(error)}")
        return jsonify({
            'status': 'error',
            'message': 'Bad request'
        }), 400

    @app.errorhandler(404)
    def not_found(error):
        logger.error(f"Not found: {str(error)}")
        return jsonify({
            'status': 'error',
            'message': 'Not found'
        }), 404

    @app.errorhandler(500)
    def internal_error(error):
        logger.error(f"Internal server error: {str(error)}")
        return jsonify({
            'status': 'error',
            'message': 'Internal server error'
        }), 500
    
    return app

if __name__ == '__main__':
    app = create_app()
    app.run()
