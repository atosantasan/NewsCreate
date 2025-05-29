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
import signal
import sys
import psutil
from tenacity import retry, stop_after_attempt, wait_exponential
import tempfile
import smtplib
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication

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
        self.smtp_email = os.getenv("SMTP_EMAIL")
        self.smtp_password = os.getenv("SMTP_PASSWORD")
        self.notification_email = os.getenv("NOTIFICATION_EMAIL")
        
        if not self.email or not self.password:
            raise ValueError("NOTE_EMAIL and NOTE_PASSWORD are required")
        if not self.smtp_email or not self.smtp_password or not self.notification_email:
            raise ValueError("SMTP_EMAIL, SMTP_PASSWORD, and NOTIFICATION_EMAIL are required")
            
        self.driver = None
        self.wait = None
        self._setup_signal_handlers()
        
        self._login_button_screenshot_path: Optional[str] = None
        
    def _setup_signal_handlers(self):
        """シグナルハンドラの設定"""
        def signal_handler(signum, frame):
            logger.info("Received signal to terminate")
            self.cleanup()
            sys.exit(0)
            
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
        
    def cleanup(self):
        """リソースのクリーンアップ"""
        if self.driver:
            try:
                self.driver.quit()
            except Exception as e:
                logger.error(f"Error during driver cleanup: {str(e)}")
            finally:
                self.driver = None
        gc.collect()
        
    def _check_memory_usage(self):
        """メモリ使用量をチェック"""
        try:
            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()
            memory_percent = process.memory_percent()
            logger.info(f"Memory usage: {memory_info.rss / 1024 / 1024:.2f} MB ({memory_percent:.1f}%)")
            
            # メモリ使用量が80%を超えた場合、スクリーンショットを保存
            if memory_percent > 80:
                logger.warning("High memory usage detected")
                self._save_screenshot('high_memory')
                gc.collect()
        except Exception as e:
            logger.error(f"Failed to check memory usage: {str(e)}")
        
    def _send_error_notification(self, error_type: str, error_info: Dict[str, Any], screenshot_paths: list[str], log_file_path: Optional[str] = None):
        """エラー通知メールを送信"""
        try:
            msg = MIMEMultipart()
            msg['Subject'] = f'Note Post Error: {error_type}'
            msg['From'] = self.smtp_email
            msg['To'] = self.notification_email

            # エラー情報を本文に追加
            body = f"""
            エラーが発生しました。

            エラータイプ: {error_type}
            発生時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            URL: {error_info.get('url', 'N/A')}
            ページタイトル: {error_info.get('title', 'N/A')}
            メモリ使用量: {error_info.get('memory_usage', 'N/A')}%

            要素の状態:
            {chr(10).join(f'- {k}: {v}' for k, v in error_info.get('elements_status', {}).items())}
            """
            msg.attach(MIMEText(body, 'plain'))

            # スクリーンショットを添付
            for screenshot_path in screenshot_paths:
                if os.path.exists(screenshot_path):
                    try:
                        with open(screenshot_path, 'rb') as f:
                            img = MIMEImage(f.read())
                            img.add_header('Content-Disposition', 'attachment', filename=os.path.basename(screenshot_path))
                            msg.attach(img)
                    except Exception as e:
                        logger.error(f"Failed to attach screenshot {screenshot_path}: {str(e)}")

            # ログファイルを添付
            if log_file_path and os.path.exists(log_file_path):
                try:
                    with open(log_file_path, 'rb') as f:
                        part = MIMEApplication(f.read(),_subtype="octet-stream")
                        part['Content-Disposition'] = f'attachment; filename="{os.path.basename(log_file_path)}"'
                        msg.attach(part)
                except Exception as e:
                    logger.error(f"Failed to attach log file {log_file_path}: {str(e)}")

            # メール送信
            try:
                with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
                    smtp.login(self.smtp_email, self.smtp_password)
                    smtp.send_message(msg)
                    logger.info(f"Error notification email sent to {self.notification_email}")
            except smtplib.SMTPAuthenticationError as e:
                logger.error("Gmail認証エラー: アプリパスワードが正しく設定されていない可能性があります。")
                logger.error(f"エラー詳細: {str(e)}")
                logger.error("Gmailの2段階認証を有効にし、アプリパスワードを生成してください。")
            except smtplib.SMTPException as e:
                logger.error(f"メール送信エラー: {str(e)}")
            except Exception as e:
                logger.error(f"メール送信中の予期せぬエラー: {str(e)}")

        except Exception as e:
            logger.error(f"メール通知送信処理で予期せぬエラーが発生: {str(e)}")

    def _save_screenshot(self, error_type: str) -> str:
        """スクリーンショットを保存し、保存先のパスを返す"""
        try:
            # 一時ディレクトリに保存
            temp_dir = tempfile.gettempdir()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"note_error_{error_type}_{timestamp}.png"
            filepath = os.path.join(temp_dir, filename)
            
            # スクリーンショットを保存
            if self.driver:
                self.driver.save_screenshot(filepath)
                logger.info(f"Screenshot saved: {filepath}")
                return filepath
            else:
                logger.warning("Driver not available for screenshot")
                return ""
        except Exception as e:
            logger.error(f"Failed to save screenshot: {str(e)}")
            return ""

    def _collect_error_info(self) -> Dict[str, Any]:
        """エラー情報を収集"""
        try:
            screenshot_path = self._save_screenshot('error')
            error_info = {
                'url': self.driver.current_url if self.driver else "No driver",
                'title': self.driver.title if self.driver else "No driver",
                'elements_status': self._check_critical_elements() if self.driver else {},
                'screenshot_path': screenshot_path,
                'memory_usage': psutil.Process(os.getpid()).memory_percent()
            }
            # エラー通知メールを送信
            screenshot_paths = []
            if screenshot_path and os.path.exists(screenshot_path):
                screenshot_paths.append(screenshot_path)
            self._send_error_notification('error', error_info, screenshot_paths, 'note_poster.log')
            return error_info
        except Exception as e:
            logger.error(f"Failed to collect error information: {str(e)}")
            # エラー情報を収集できなかった場合も、可能な限りの情報でメール送信を試みる
            error_info = {
                 'url': self.driver.current_url if self.driver else "No driver",
                 'title': self.driver.title if self.driver else "No driver",
                 'elements_status': {} # 要素状態は収集できなかったとする
            }
            screenshot_paths = []
            if self._login_button_screenshot_path and os.path.exists(self._login_button_screenshot_path):
                screenshot_paths.append(self._login_button_screenshot_path)
            # エラー情報収集時のスクリーンショットは保存できていないので含めない
            
            self._send_error_notification('error_collection_failed', error_info, screenshot_paths, 'note_poster.log')
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
            options.add_argument("--window-size=1280,720")
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
            
            # メモリ制限の設定
            options.add_argument("--js-flags=--max-old-space-size=256")
            options.add_argument("--memory-pressure-off")
            options.add_argument("--disable-software-rasterizer")
            options.add_argument("--disable-dev-tools")
            options.add_argument("--disable-logging")
            options.add_argument("--log-level=3")
            options.add_argument("--silent")
            
            # 日本語表示のためのオプションを追加
            options.add_argument("--lang=ja")
            options.add_argument("--accept-lang=ja")
            options.add_argument("--force-device-scale-factor=1") # スケーリングを強制しない
            options.add_argument("--high-dpi-support=1") # DPIサポートを有効に

            # 自動化検出対策
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option("useAutomationExtension", False)
            
            self.driver = webdriver.Chrome(options=options)
            self.wait = WebDriverWait(self.driver, 15)  # タイムアウトを15秒に延長
            self._apply_stealth_script()
        except Exception as e:
            logger.error(f"Failed to setup Chrome driver: {str(e)}")
            raise

    def _wait_for_page_load(self, timeout: int = 5):
        """ページの読み込み完了を待機"""
        try:
            self.driver.execute_script("return document.readyState") == "complete"
            time.sleep(1)  # 待機時間を延長
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

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def _login(self):
        """Noteにログイン（リトライ処理付き）"""
        try:
            logger.info("Attempting to login to Note")
            logger.info("Navigating to login page...")
            self.driver.get("https://note.com/login")
            # ログインページが完全に表示されるまで待機 (メールアドレス入力欄で確認)
            WebDriverWait(self.driver, 20).until(EC.presence_of_element_located((By.ID, "email")))
            self._check_memory_usage()
            
            logger.info("Clearing cookies...")
            self.driver.delete_all_cookies()
            
            # ログインフォームの入力
            logger.info("Entering email...")
            email_input = self.wait.until(EC.presence_of_element_located((By.ID, "email")))
            email_input.clear()
            email_input.send_keys(self.email)
            time.sleep(1) # 待機時間を延長
            self._check_memory_usage()
            
            logger.info("Entering password...")
            password_input = self.wait.until(EC.presence_of_element_located((By.ID, "password")))
            password_input.clear()
            password_input.send_keys(self.password)
            time.sleep(1) # 待機時間を延長
            self._check_memory_usage()
            
            # ログインボタンを押す前にスクリーンショットを保存
            self._login_button_screenshot_path = self._save_screenshot('login_button_before')

            # ログインボタンのクリック
            logger.info("Clicking login button...")
            login_button = self.wait.until(EC.element_to_be_clickable((By.XPATH, '//button[contains(.,"ログイン")]')))
            login_button.click()
            
            # ログイン完了の待機（複数の要素をチェック）
            logger.info("Waiting for login completion...")
            try:
                self.wait.until(EC.presence_of_element_located((By.XPATH, '//div[contains(@class, "note-header")]')))
            except TimeoutException:
                # エラーメッセージを確認
                error_message = self._check_login_error()
                if error_message:
                    logger.error(f"Login error message: {error_message}")
                    self._save_screenshot('login_error')
                    raise ValueError(f"Login failed: {error_message}")
                
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
        except Exception as e:
            error_info = self._collect_error_info()
            logger.error(f"Unexpected error during login. Status: {error_info}")
            raise
            
    def post_article(self, article_body: str, title: str) -> Optional[str]:
        """記事をNoteに投稿する"""
        try:
            logger.info(f"Starting article posting process for title: {title}")
            # ログイン処理
            self._setup_driver()
            self._login()
            self.cleanup() # ログイン後、ドライバーを一度終了してメモリ解放
            
            # 記事投稿処理のためにドライバーを再初期化
            self._setup_driver()
            
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
            time.sleep(2)
            current_url = self.driver.current_url
            logger.info(f"Article posted successfully: {current_url}")
            
            return current_url
            
        except Exception as e:
            error_info = self._collect_error_info()
            logger.error(f"Failed to post article. Status: {error_info}")
            return None
            
        finally:
            self.cleanup()

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

    def _apply_stealth_script(self):
        """WebDriver検出を回避するためのJavaScriptを実行"""
        try:
            self.driver.execute_script("""
              Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
              })
            """)
            logger.info("Applied stealth script")
        except Exception as e:
            logger.error(f"Failed to apply stealth script: {str(e)}")
