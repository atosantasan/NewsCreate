import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # 基本設定
    SECRET_KEY = os.getenv('SECRET_KEY', os.urandom(24).hex())
    FLASK_ENV = os.getenv('FLASK_ENV', 'development')
    DEBUG = FLASK_ENV == 'development'
    
    # セッション設定
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = 3600  # 1時間
    
    # CORS設定
    CORS_ORIGINS = os.getenv('CORS_ORIGINS', '').split(',')
    
    # API設定
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
    TWITTER_API_KEY = os.getenv('TWITTER_API_KEY')
    TWITTER_API_SECRET = os.getenv('TWITTER_API_SECRET')
    TWITTER_ACCESS_TOKEN = os.getenv('TWITTER_ACCESS_TOKEN')
    TWITTER_ACCESS_TOKEN_SECRET = os.getenv('TWITTER_ACCESS_TOKEN_SECRET')
    
    # Note設定
    NOTE_EMAIL = os.getenv('NOTE_EMAIL')
    NOTE_PASSWORD = os.getenv('NOTE_PASSWORD')
    
    # RSS設定
    RSS_URLS = os.getenv('RSS_URLS', '').split(',')
    
    # レート制限設定
    RATELIMIT_DEFAULT = "200 per day"
    RATELIMIT_STORAGE_URL = os.getenv('RATELIMIT_STORAGE_URL', 'memory://')
    RATELIMIT_STRATEGY = 'fixed-window'
    RATELIMIT_HEADERS_ENABLED = True

class DevelopmentConfig(Config):
    DEBUG = True
    SESSION_COOKIE_SECURE = False
    CORS_ORIGINS = ['http://localhost:3000', 'http://localhost:5000']

class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    CORS_ORIGINS = os.getenv('CORS_ORIGINS', '').split(',')

class TestingConfig(Config):
    TESTING = True
    DEBUG = True
    SESSION_COOKIE_SECURE = False
    CORS_ORIGINS = ['http://localhost:3000']

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
} 