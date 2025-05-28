import logging
import logging.handlers
import os
from datetime import datetime

def setup_logger(app):
    """アプリケーションのロガーを設定します。"""
    
    # ログディレクトリの作成
    log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    # ログファイル名の設定（日付を含む）
    log_file = os.path.join(log_dir, f'app_{datetime.now().strftime("%Y%m%d")}.log')
    
    # ログフォーマットの設定
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # ファイルハンドラーの設定
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=10485760,  # 10MB
        backupCount=10,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)
    
    # コンソールハンドラーの設定
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.DEBUG if app.debug else logging.INFO)
    
    # ルートロガーの設定
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG if app.debug else logging.INFO)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    
    # アプリケーション固有のロガー設定
    app_logger = logging.getLogger('NewsCreate')
    app_logger.setLevel(logging.DEBUG if app.debug else logging.INFO)
    
    # 不要なログの抑制
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    
    return app_logger

def get_logger(name):
    """指定された名前のロガーを取得します。"""
    return logging.getLogger(f'NewsCreate.{name}')
