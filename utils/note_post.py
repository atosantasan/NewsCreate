from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
import time
import os
import logging
from typing import Optional, Dict, Any
from dotenv import load_dotenv
import base64
from datetime import datetime

# ログ設定を追加
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('note_poster.log'),
        logging.StreamHandler()
    ]
)

# Seleniumのデバッグログを無効化
logging.getLogger('selenium').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

class NotePoster:
    def __init__(self):
        load_dotenv()
        self.email = os.getenv("NOTE_EMAIL")
        self.password = os.getenv("NOTE_PASSWORD")
        
        if not self.email or not self.password:
            raise ValueError("NOTE_EMAIL and NOTE_PASSWORD are required")
            
        self.driver = None
        self.wait = None
        
    def _collect_error_info(self) -> Dict[str, Any]:
        """エラー情報を収集"""
        try:
            return {
                'url': self.driver.current_url,
                'title': self.driver.title,
                'elements_status': self._check_critical_elements()
            }
        except Exception as e:
            logger.error(f"Failed to collect error information: {str(e)}")
            return {}

    def _setup_driver(self):
        """Seleniumドライバーの初期化"""
        try:
            options = Options()
            options.add_argument("--headless")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument("--disable-features=NetworkService,NetworkServiceInProcess")
            options.add_argument("--window-size=1920,1080")
            options.add_argument("--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
            self.driver = webdriver.Chrome(options=options)
            self.wait = WebDriverWait(self.driver, 10)
        except Exception as e:
            logger.error(f"Failed to setup Chrome driver: {str(e)}")
            raise

    def _login(self):
        """Noteにログイン"""
        try:
            logger.info("Attempting to login to Note")
            self.driver.get("https://note.com/login")
            self.driver.delete_all_cookies()
            
            # ログインフォームの入力
            email_input = self.wait.until(EC.presence_of_element_located((By.ID, "email")))
            email_input.send_keys(self.email)
            
            password_input = self.wait.until(EC.presence_of_element_located((By.ID, "password")))
            password_input.send_keys(self.password)
            
            # ログインボタンのクリック
            login_button = self.wait.until(EC.element_to_be_clickable((By.XPATH, '//button[contains(.,"ログイン")]')))
            login_button.click()
            
            # ログイン完了の待機（複数の要素をチェック）
            try:
                self.wait.until(EC.presence_of_element_located((By.XPATH, '//div[contains(@class, "note-header")]')))
            except TimeoutException:
                # 代替の要素をチェック
                success = False
                for selector in [
                    '//div[contains(@class, "note-header")]',
                    '//div[contains(@class, "note-header__user")]',
                    '//div[contains(@class, "note-header__menu")]',
                    '//a[contains(@href, "/mypage")]'
                ]:
                    try:
                        self.wait.until(EC.presence_of_element_located((By.XPATH, selector)))
                        success = True
                        break
                    except TimeoutException:
                        continue
                
                if not success:
                    error_info = self._collect_error_info()
                    logger.error(f"Login failed. Status: {error_info}")
                    raise TimeoutException("Could not confirm successful login")
            
            logger.info("Successfully logged in to Note")
            
        except TimeoutException as e:
            error_info = self._collect_error_info()
            logger.error(f"Login timeout. Status: {error_info}")
            raise
        except WebDriverException as e:
            error_info = self._collect_error_info()
            logger.error(f"WebDriver error. Status: {error_info}")
            raise
            
    def post_article(self, article_body: str, title: str) -> Optional[str]:
        """記事をNoteに投稿する"""
        try:
            logger.info(f"Starting article posting process for title: {title}")
            self._setup_driver()
            self._login()
            
            # 新規記事作成ページへ移動
            self.driver.get("https://note.com/notes/new")
            
            # タイトルと本文の入力
            title_input = self.wait.until(EC.presence_of_element_located((By.XPATH, '//textarea[@placeholder="記事タイトル"]')))
            title_input.send_keys(title)
            
            body_input = self.wait.until(EC.presence_of_element_located((By.XPATH, '//div[@contenteditable="true" and contains(@class, "ProseMirror")]')))
            body_input.click()
            body_input.send_keys(article_body)
            
            # 公開処理
            publish_button = self.wait.until(EC.element_to_be_clickable((By.XPATH, '//span[contains(text(), "公開に進む")]')))
            publish_button.click()
            
            post_button = self.wait.until(EC.element_to_be_clickable((By.XPATH, '//span[contains(text(), "投稿する")]')))
            post_button.click()
            
            # 投稿完了の待機
            time.sleep(3)
            current_url = self.driver.current_url
            logger.info(f"Article posted successfully: {current_url}")
            
            return current_url
            
        except Exception as e:
            error_info = self._collect_error_info()
            logger.error(f"Failed to post article. Status: {error_info}")
            return None
            
        finally:
            if self.driver:
                self.driver.quit()

    def _check_critical_elements(self) -> Dict[str, bool]:
        """重要な要素の状態を確認"""
        try:
            return {
                'email_field': bool(self.driver.find_elements(By.ID, "email")),
                'password_field': bool(self.driver.find_elements(By.ID, "password")),
                'login_button': bool(self.driver.find_elements(By.XPATH, '//button[contains(.,"ログイン")]')),
                'note_header': bool(self.driver.find_elements(By.XPATH, '//div[contains(@class, "note-header")]')),
                'note_header_user': bool(self.driver.find_elements(By.XPATH, '//div[contains(@class, "note-header__user")]')),
                'note_header_menu': bool(self.driver.find_elements(By.XPATH, '//div[contains(@class, "note-header__menu")]')),
                'mypage_link': bool(self.driver.find_elements(By.XPATH, '//a[contains(@href, "/mypage")]'))
            }
        except Exception as e:
            logger.error(f"Failed to check elements: {str(e)}")
            return {}
