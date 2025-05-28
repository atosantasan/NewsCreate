from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException, NoSuchElementException
import time
import os
import logging
from typing import Optional, Dict, Any
from dotenv import load_dotenv
import base64
from datetime import datetime
import gc

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
            options.add_argument("--headless=new")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument("--disable-features=NetworkService,NetworkServiceInProcess")
            options.add_argument("--window-size=1920,1080")
            options.add_argument("--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option("useAutomationExtension", False)
            
            # メモリ使用量の最適化
            options.add_argument("--disable-extensions")
            options.add_argument("--disable-popup-blocking")
            options.add_argument("--disable-infobars")
            options.add_argument("--disable-notifications")
            options.add_argument("--disable-default-apps")
            options.add_argument("--disable-sync")
            options.add_argument("--disable-background-networking")
            options.add_argument("--disable-background-timer-throttling")
            options.add_argument("--disable-backgrounding-occluded-windows")
            options.add_argument("--disable-breakpad")
            options.add_argument("--disable-component-extensions-with-background-pages")
            options.add_argument("--disable-features=TranslateUI")
            options.add_argument("--disable-ipc-flooding-protection")
            options.add_argument("--disable-renderer-backgrounding")
            options.add_argument("--enable-features=NetworkService,NetworkServiceInProcess")
            options.add_argument("--force-color-profile=srgb")
            options.add_argument("--metrics-recording-only")
            options.add_argument("--no-first-run")
            options.add_argument("--password-store=basic")
            options.add_argument("--use-mock-keychain")
            
            self.driver = webdriver.Chrome(options=options)
            self.wait = WebDriverWait(self.driver, 15)  # タイムアウトを15秒に調整
        except Exception as e:
            logger.error(f"Failed to setup Chrome driver: {str(e)}")
            raise

    def _wait_for_page_load(self, timeout: int = 5):
        """ページの読み込み完了を待機"""
        try:
            self.driver.execute_script("return document.readyState") == "complete"
            time.sleep(1)  # 待機時間を短縮
        except Exception as e:
            logger.error(f"Page load wait failed: {str(e)}")

    def _check_login_error(self) -> Optional[str]:
        """ログインエラーメッセージを確認"""
        try:
            error_messages = [
                "//div[contains(@class, 'error-message')]",
                "//div[contains(@class, 'alert')]",
                "//p[contains(@class, 'error')]"
            ]
            for xpath in error_messages:
                try:
                    error_element = self.driver.find_element(By.XPATH, xpath)
                    if error_element.is_displayed():
                        return error_element.text
                except NoSuchElementException:
                    continue
            return None
        except Exception as e:
            logger.error(f"Failed to check login error: {str(e)}")
            return None

    def _login(self):
        """Noteにログイン"""
        try:
            logger.info("Attempting to login to Note")
            self.driver.get("https://note.com/login")
            self._wait_for_page_load()
            self.driver.delete_all_cookies()
            
            # ログインフォームの入力
            email_input = self.wait.until(EC.presence_of_element_located((By.ID, "email")))
            email_input.clear()
            email_input.send_keys(self.email)
            time.sleep(0.5)  # 待機時間を短縮
            
            password_input = self.wait.until(EC.presence_of_element_located((By.ID, "password")))
            password_input.clear()
            password_input.send_keys(self.password)
            time.sleep(0.5)  # 待機時間を短縮
            
            # ログインボタンのクリック
            login_button = self.wait.until(EC.element_to_be_clickable((By.XPATH, '//button[contains(.,"ログイン")]')))
            login_button.click()
            
            # ログイン完了の待機（複数の要素をチェック）
            try:
                self.wait.until(EC.presence_of_element_located((By.XPATH, '//div[contains(@class, "note-header")]')))
            except TimeoutException:
                # エラーメッセージを確認
                error_message = self._check_login_error()
                if error_message:
                    logger.error(f"Login error message: {error_message}")
                
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
            self._wait_for_page_load()
            
            # タイトルと本文の入力
            title_input = self.wait.until(EC.presence_of_element_located((By.XPATH, '//textarea[@placeholder="記事タイトル"]')))
            title_input.clear()
            title_input.send_keys(title)
            time.sleep(0.5)
            
            body_input = self.wait.until(EC.presence_of_element_located((By.XPATH, '//div[@contenteditable="true" and contains(@class, "ProseMirror")]')))
            body_input.click()
            body_input.send_keys(article_body)
            time.sleep(0.5)
            
            # 公開処理
            publish_button = self.wait.until(EC.element_to_be_clickable((By.XPATH, '//span[contains(text(), "公開に進む")]')))
            publish_button.click()
            time.sleep(1)
            
            post_button = self.wait.until(EC.element_to_be_clickable((By.XPATH, '//span[contains(text(), "投稿する")]')))
            post_button.click()
            
            # 投稿完了の待機
            time.sleep(3)  # 待機時間を短縮
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
                self.driver = None
            gc.collect()  # メモリの解放を強制

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
