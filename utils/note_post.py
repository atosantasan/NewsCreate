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
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('note_poster.log'),
        logging.StreamHandler()
    ]
)

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
        
    def _save_screenshot(self, prefix: str):
        """エラー情報を収集"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # 現在のURLとページタイトルを取得
            current_url = self.driver.current_url
            page_title = self.driver.title
            
            # エラー情報をログに出力
            logger.error(f"Error occurred at {timestamp}")
            logger.error(f"Current URL: {current_url}")
            logger.error(f"Page title: {page_title}")
            
            # 重要な要素の状態を確認
            elements_status = self._check_critical_elements()
            logger.error(f"Elements status: {elements_status}")
            
            return {
                'timestamp': timestamp,
                'url': current_url,
                'title': page_title,
                'elements_status': elements_status
            }
        except Exception as e:
            logger.error(f"Failed to collect error information: {str(e)}")
            return None

    def _setup_driver(self):
        """Seleniumドライバーの初期化"""
        try:
            logger.info("Setting up Chrome driver...")
            options = Options()
            options.add_argument("--headless")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument("--disable-features=NetworkService,NetworkServiceInProcess")
            options.add_argument("--window-size=1920,1080")
            # ユーザーエージェントを設定
            options.add_argument("--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
            logger.info("Chrome options configured")
            self.driver = webdriver.Chrome(options=options)
            logger.info("Chrome driver initialized successfully")
            self.wait = WebDriverWait(self.driver, 10)
        except Exception as e:
            logger.error(f"Failed to setup Chrome driver: {str(e)}")
            raise

    def _login(self):
        """Noteにログイン"""
        try:
            logger.info("Attempting to login to Note")
            logger.info("Navigating to login page...")
            self.driver.get("https://note.com/login")
            logger.info("Login page loaded")
            
            # クッキーをクリア
            self.driver.delete_all_cookies()
            logger.info("Cookies cleared")
            
            # ログインフォームの入力
            logger.info("Waiting for email input field...")
            email_input = self.wait.until(EC.presence_of_element_located((By.ID, "email")))
            logger.info("Email input field found")
            email_input.send_keys(self.email)
            
            logger.info("Waiting for password input field...")
            password_input = self.wait.until(EC.presence_of_element_located((By.ID, "password")))
            logger.info("Password input field found")
            password_input.send_keys(self.password)
            
            # ログインボタンのクリック
            logger.info("Looking for login button...")
            login_button = self.wait.until(EC.element_to_be_clickable((By.XPATH, '//button[contains(.,"ログイン")]')))
            logger.info("Login button found, clicking...")
            login_button.click()
            
            # ログイン完了の待機（複数の要素をチェック）
            logger.info("Waiting for login completion...")
            try:
                # まずnote-headerを待機
                self.wait.until(EC.presence_of_element_located((By.XPATH, '//div[contains(@class, "note-header")]')))
            except TimeoutException:
                logger.info("note-header not found, checking for other elements...")
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
                        logger.info(f"Login confirmed by finding element: {selector}")
                        break
                    except TimeoutException:
                        continue
                
                if not success:
                    # エラー情報を収集
                    error_info = self._save_screenshot("login_failed")
                    logger.error(f"Login failed. Error info: {error_info}")
                    raise TimeoutException("Could not confirm successful login")
            
            logger.info("Successfully logged in to Note")
            
        except TimeoutException as e:
            logger.error(f"Timeout during login: {str(e)}")
            self._save_screenshot("login_timeout")
            raise
        except WebDriverException as e:
            logger.error(f"WebDriver error during login: {str(e)}")
            self._save_screenshot("login_error")
            raise
            
    def post_article(self, article_body: str, title: str) -> Optional[str]:
        """
        記事をNoteに投稿する
        
        Args:
            article_body (str): 記事本文
            title (str): 記事タイトル
            
        Returns:
            Optional[str]: 投稿された記事のURL。失敗時はNone
        """
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
            logger.error(f"Failed to post article: {str(e)}")
            self._save_screenshot("error")
            return None
            
        finally:
            if self.driver:
                self.driver.quit()

    def _check_critical_elements(self) -> Dict[str, bool]:
        """重要な要素の状態を確認"""
        try:
            elements_status = {
                'email_field': bool(self.driver.find_elements(By.ID, "email")),
                'password_field': bool(self.driver.find_elements(By.ID, "password")),
                'login_button': bool(self.driver.find_elements(By.XPATH, '//button[contains(.,"ログイン")]')),
                'note_header': bool(self.driver.find_elements(By.XPATH, '//div[contains(@class, "note-header")]')),
                'note_header_user': bool(self.driver.find_elements(By.XPATH, '//div[contains(@class, "note-header__user")]')),
                'note_header_menu': bool(self.driver.find_elements(By.XPATH, '//div[contains(@class, "note-header__menu")]')),
                'mypage_link': bool(self.driver.find_elements(By.XPATH, '//a[contains(@href, "/mypage")]'))
            }
            return elements_status
        except Exception as e:
            logger.error(f"Failed to check elements: {str(e)}")
            return {}
            
    def _collect_error_info(self, prefix: str) -> Dict[str, Any]:
        """エラー時の情報を収集"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            error_info = {
                'timestamp': timestamp,
                'url': self.driver.current_url,
                'title': self.driver.title,
                'error_type': prefix,
                'elements_status': self._check_critical_elements()
            }
            
            # エラー情報のログ出力
            logger.error(f"Error occurred at URL: {error_info['url']}")
            logger.error(f"Page title: {error_info['title']}")
            logger.error(f"Error type: {error_info['error_type']}")
            logger.error(f"Elements status: {error_info['elements_status']}")
            
            return error_info
        except Exception as e:
            logger.error(f"Failed to collect error information: {str(e)}")
            return {}
            
    def _handle_error(self, error_type: str, error: Exception) -> Dict[str, Any]:
        """エラー処理の一元化"""
        try:
            error_info = self._collect_error_info(error_type)
            error_info['error_message'] = str(error)
            return error_info
        except Exception as e:
            logger.error(f"Failed to handle error: {str(e)}")
            return {}
