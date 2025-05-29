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
                try:
                    self.driver.save_screenshot(filepath)
                    # ファイルが実際に保存されたか確認
                    if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                        logger.info(f"Screenshot saved: {filepath}")
                        return filepath
                    else:
                        logger.error(f"Screenshot file was not created or is empty: {filepath}")
                        return ""
                except Exception as e:
                    logger.error(f"Failed to save screenshot: {str(e)}")
                    return ""
            else:
                logger.warning("Driver not available for screenshot")
                return ""
        except Exception as e:
            logger.error(f"Failed to save screenshot: {str(e)}")
            return ""

    def _send_error_notification(self, error_type: str, error_info: Dict[str, Any], screenshot_paths: list[str], log_file_path: Optional[str] = None):
        """エラー通知メールを送信"""
        try:
            logger.info(f"Preparing to send error notification email for: {error_type}")
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
                        logger.info(f"Attaching screenshot: {screenshot_path}")
                        # ファイルの読み取り権限を確認
                        if not os.access(screenshot_path, os.R_OK):
                            logger.error(f"No read permission for screenshot: {screenshot_path}")
                            continue
                            
                        with open(screenshot_path, 'rb') as f:
                            img = MIMEImage(f.read())
                            img.add_header('Content-Disposition', 'attachment', filename=os.path.basename(screenshot_path))
                            msg.attach(img)
                            logger.info(f"Successfully attached screenshot: {screenshot_path}")
                    except Exception as e:
                        logger.error(f"Failed to attach screenshot {screenshot_path}: {str(e)}")
                else:
                    logger.warning(f"Screenshot file not found: {screenshot_path}")

            # ログファイルを添付
            if log_file_path:
                try:
                    log_file_path = os.path.abspath(log_file_path)
                    logger.info(f"Attempting to attach log file: {log_file_path}")
                    if os.path.exists(log_file_path):
                        # ファイルの読み取り権限を確認
                        if not os.access(log_file_path, os.R_OK):
                            logger.error(f"No read permission for log file: {log_file_path}")
                        else:
                            with open(log_file_path, 'rb') as f:
                                part = MIMEApplication(f.read(),_subtype="octet-stream")
                                part['Content-Disposition'] = f'attachment; filename="{os.path.basename(log_file_path)}"'
                                msg.attach(part)
                                logger.info(f"Successfully attached log file: {log_file_path}")
                    else:
                        logger.warning(f"Log file not found: {log_file_path}")
                except Exception as e:
                    logger.error(f"Failed to attach log file {log_file_path}: {str(e)}")

            # メール送信
            try:
                logger.info("Connecting to SMTP server...")
                with smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=30) as smtp:
                    logger.info("Logging in to SMTP server...")
                    smtp.login(self.smtp_email, self.smtp_password)
                    logger.info("Sending email...")
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
                logger.error(f"エラーの種類: {type(e).__name__}")
                logger.error(f"エラーの詳細: {str(e)}")

        except Exception as e:
            logger.error(f"メール通知送信処理で予期せぬエラーが発生: {str(e)}")
            logger.error(f"エラーの種類: {type(e).__name__}")
            logger.error(f"エラーの詳細: {str(e)}")

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

    def _wait_for_page_load(self, timeout: int = 30):  # タイムアウトを30秒に延長
        """ページの読み込みを待機"""
        try:
            WebDriverWait(self.driver, timeout).until(
                lambda driver: driver.execute_script('return document.readyState') == 'complete'
            )
        except TimeoutException:
            logger.warning(f"Page load timeout after {timeout} seconds")
            self._check_memory_usage()
            gc.collect()

    def _check_login_error(self) -> Optional[str]:
        """ログインエラーの確認"""
        try:
            # エラーメッセージの要素を確認
            error_elements = self.driver.find_elements(By.CSS_SELECTOR, '.error-message, .alert-danger')
            if error_elements:
                return error_elements[0].text
            return None
        except Exception as e:
            logger.error(f"Error checking login status: {str(e)}")
            return None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def _login(self):
        """Noteへのログイン処理"""
        try:
            logger.info("Attempting to login to Note")
            self._setup_driver()
            
            # ログインページに移動
            logger.info("Navigating to login page...")
            self.driver.get("https://note.com/login")
            self._wait_for_page_load(timeout=30)  # タイムアウトを30秒に延長
            
            # メモリ使用量をチェック
            self._check_memory_usage()
            
            # クッキーをクリア
            logger.info("Clearing cookies...")
            self.driver.delete_all_cookies()
            
            # メールアドレスを入力
            logger.info("Entering email...")
            email_field = WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type="email"]'))
            )
            email_field.clear()
            email_field.send_keys(self.email)
            
            # メモリ使用量をチェック
            self._check_memory_usage()
            
            # パスワードを入力
            logger.info("Entering password...")
            password_field = WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type="password"]'))
            )
            password_field.clear()
            password_field.send_keys(self.password)
            
            # メモリ使用量をチェック
            self._check_memory_usage()
            
            # ログインボタンをクリックする前のスクリーンショットを保存
            self._login_button_screenshot_path = self._save_screenshot('login_button_before')
            
            # ログインボタンをクリック
            logger.info("Clicking login button...")
            login_button = WebDriverWait(self.driver, 20).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[type="submit"]'))
            )
            login_button.click()
            
            # ログイン完了を待機
            logger.info("Waiting for login completion...")
            try:
                # ログイン成功の判定条件を緩和
                WebDriverWait(self.driver, 60).until(  # タイムアウトを60秒に延長
                    lambda driver: any([
                        'mypage' in driver.current_url,
                        'dashboard' in driver.current_url,
                        driver.find_elements(By.CSS_SELECTOR, '.note-header-user'),
                        driver.find_elements(By.CSS_SELECTOR, '.note-header-menu')
                    ])
                )
                logger.info("Login successful")
                return True
            except TimeoutException:
                # エラー情報を収集
                error_info = self._collect_error_info()
                logger.error(f"Login failed. Status: {error_info}")
                
                # エラー通知メールを送信
                screenshot_paths = []
                if self._login_button_screenshot_path:
                    screenshot_paths.append(self._login_button_screenshot_path)
                if error_info.get('screenshot_path'):
                    screenshot_paths.append(error_info['screenshot_path'])
                self._send_error_notification('login_failed', error_info, screenshot_paths, 'note_poster.log')
                
                # リトライのために例外を発生
                raise Exception("Login failed")
                
        except TimeoutException as e:
            logger.error(f"Login timeout: {str(e)}")
            self._check_memory_usage()
            gc.collect()
            # TimeoutExceptionの場合もエラー情報を収集し、メール送信
            error_info = self._collect_error_info()
            logger.error(f"Login timeout. Status: {error_info}") # 再度ログ出力
            screenshot_paths = []
            if self._login_button_screenshot_path and os.path.exists(self._login_button_screenshot_path):
                 screenshot_paths.append(self._login_button_screenshot_path)
            if error_info.get('screenshot_path') and os.path.exists(error_info['screenshot_path']):
                 screenshot_paths.append(error_info['screenshot_path'])
            self._send_error_notification('login_timeout', error_info, screenshot_paths, 'note_poster.log')
            raise
        except WebDriverException as e:
            logger.error(f"WebDriver error during login: {str(e)}")
            # WebDriverExceptionの場合もエラー情報を収集し、メール送信
            error_info = self._collect_error_info()
            logger.error(f"WebDriver error during login. Status: {error_info}") # 再度ログ出力
            screenshot_paths = []
            if self._login_button_screenshot_path and os.path.exists(self._login_button_screenshot_path):
                 screenshot_paths.append(self._login_button_screenshot_path)
            if error_info.get('screenshot_path') and os.path.exists(error_info['screenshot_path']):
                 screenshot_paths.append(error_info['screenshot_path'])
            self._send_error_notification('webdriver_error', error_info, screenshot_paths, 'note_poster.log')
            raise
        except Exception as e:
            logger.error(f"Unexpected error during login: {str(e)}")
            self._check_memory_usage()
            gc.collect()
            # その他の予期せぬエラーの場合もエラー情報を収集し、メール送信
            error_info = self._collect_error_info()
            logger.error(f"Unexpected error during login. Status: {error_info}") # 再度ログ出力
            screenshot_paths = []
            if self._login_button_screenshot_path and os.path.exists(self._login_button_screenshot_path):
                 screenshot_paths.append(self._login_button_screenshot_path)
            if error_info.get('screenshot_path') and os.path.exists(error_info['screenshot_path']):
                 screenshot_paths.append(error_info['screenshot_path'])
            self._send_error_notification('unexpected_login_error', error_info, screenshot_paths, 'note_poster.log')
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
            # エラー通知メール送信は_collect_error_info内で実施
            
            # post_article 内でのエラー発生時もログファイルとログイン前SSを添付するよう修正
            screenshot_paths = []
            if self._login_button_screenshot_path and os.path.exists(self._login_button_screenshot_path):
                 screenshot_paths.append(self._login_button_screenshot_path)
            if error_info.get('screenshot_path') and os.path.exists(error_info['screenshot_path']):
                 screenshot_paths.append(error_info['screenshot_path'])
            self._send_error_notification('post_article_failed', error_info, screenshot_paths, 'note_poster.log')
            
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
