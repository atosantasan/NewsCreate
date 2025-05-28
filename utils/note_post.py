from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
import time
import os
import logging
from typing import Optional
from dotenv import load_dotenv

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
        
    def _setup_driver(self):
        """Seleniumドライバーの初期化"""
        logger.info("Setting up Chrome driver...")
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-features=NetworkService,NetworkServiceInProcess")
        options.add_argument("--window-size=1920,1080")
        logger.info("Chrome options configured")
        self.driver = webdriver.Chrome(options=options)
        logger.info("Chrome driver initialized successfully")
        self.wait = WebDriverWait(self.driver, 10)
        
    def _login(self):
        """Noteにログイン"""
        try:
            logger.info("Attempting to login to Note")
            logger.info("Navigating to login page...")
            self.driver.get("https://note.com/login")
            logger.info("Login page loaded")
            
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
            
            # ログイン完了の待機
            logger.info("Waiting for login completion...")
            self.wait.until(EC.presence_of_element_located((By.XPATH, '//div[contains(@class, "note-header")]')))
            logger.info("Successfully logged in to Note")
            
        except TimeoutException as e:
            logger.error(f"Timeout during login: {str(e)}")
            if self.driver:
                self.driver.save_screenshot("note_login_timeout.png")
                logger.info("Login timeout screenshot saved")
            raise
        except WebDriverException as e:
            logger.error(f"WebDriver error during login: {str(e)}")
            if self.driver:
                self.driver.save_screenshot("note_login_error.png")
                logger.info("Login error screenshot saved")
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
            if self.driver:
                self.driver.save_screenshot("note_error_screenshot.png")
                logger.info("Error screenshot saved as note_error_screenshot.png")
            return None
            
        finally:
            if self.driver:
                self.driver.quit()
