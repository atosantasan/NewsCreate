from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException, WebDriverException, NoSuchElementException
import time
import os
import logging
from typing import Optional, Dict, Any
from dotenv import load_dotenv
import gc
import signal
import sys
import psutil
from tenacity import retry, stop_after_attempt, wait_exponential
import tempfile
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email import encoders
import random
from selenium_stealth import stealth
from selenium.webdriver.common.action_chains import ActionChains

# ログ設定を追加
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('twitter_bot.log'),
        logging.StreamHandler()
    ]
)

# Seleniumのデバッグログを無効化
logging.getLogger('selenium').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

class TwitterBot:
    def __init__(self):
        load_dotenv()
        self.twitter_id = os.getenv('TWITTER_ID')
        self.twitter_user_id = os.getenv('TWITTER_USER_ID')
        self.twitter_password = os.getenv('TWITTER_PASSWORD')
        
        # メール通知用の環境変数
        self.smtp_email = os.getenv("SMTP_EMAIL")
        self.smtp_password = os.getenv("SMTP_PASSWORD")
        self.notification_email = os.getenv("NOTIFICATION_EMAIL")
        
        if not all([self.twitter_id, self.twitter_user_id, self.twitter_password]):
            raise ValueError("TWITTER_ID, TWITTER_USER_ID, and TWITTER_PASSWORD are required")
        # メール通知用の環境変数もチェック（必須とするか任意とするかは要件次第）
        # if not all([self.smtp_email, self.smtp_password, self.notification_email]):
        #     logger.warning("SMTP_EMAIL, SMTP_PASSWORD, and NOTIFICATION_EMAIL are not set. Email notifications will be disabled.")
            
        self.driver = None
        self.wait = None
        self.modal_wait = None
        self._setup_signal_handlers()
        
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
            
            if memory_percent > 80:
                logger.warning("High memory usage detected")
                self._save_screenshot('high_memory')
                gc.collect()
        except Exception as e:
            logger.error(f"Failed to check memory usage: {str(e)}")
            
    def _save_screenshot(self, error_type: str) -> str:
        """スクリーンショットを保存し、保存先のパスを返す"""
        try:
            temp_dir = tempfile.gettempdir()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"twitter_error_{error_type}_{timestamp}.png"
            filepath = os.path.join(temp_dir, filename)
            
            if self.driver:
                try:
                    self.driver.save_screenshot(filepath)
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
            
    def _send_notification_email(self, subject: str, body: str, screenshot_paths: list[str], log_file_path: Optional[str] = None):
        """通知メールを送信"""
        if not all([self.smtp_email, self.smtp_password, self.notification_email]):
            logger.warning("SMTP credentials not set. Skipping email notification.")
            return
            
        try:
            logger.info(f"Preparing to send notification email: {subject}")
            msg = MIMEMultipart()
            msg['Subject'] = subject
            msg['From'] = self.smtp_email
            msg['To'] = self.notification_email

            msg.attach(MIMEText(body, 'plain'))

            # スクリーンショットを添付
            for screenshot_path in screenshot_paths:
                if os.path.exists(screenshot_path):
                    try:
                        logger.info(f"Attaching screenshot: {screenshot_path}")
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
            if log_file_path and os.path.exists(log_file_path):
                try:
                    log_file_path = os.path.abspath(log_file_path)
                    logger.info(f"Attempting to attach log file: {log_file_path}")
                    if os.access(log_file_path, os.R_OK):
                        with open(log_file_path, 'rb') as f:
                            part = MIMEApplication(f.read(),_subtype="octet-stream")
                            part.set_payload((f.read()))
                            encoders.encode_base64(part)
                            part.add_header('Content-Disposition', 'attachment', filename=os.path.basename(log_file_path))
                            msg.attach(part)
                            logger.info(f"Successfully attached log file: {log_file_path}")
                    else:
                        logger.error(f"No read permission for log file: {log_file_path}")
                except Exception as e:
                    logger.error(f"Failed to attach log file {log_file_path}: {str(e)}")
            elif log_file_path:
                 logger.warning(f"Log file not found for attachment: {log_file_path}")

            # メール送信
            try:
                logger.info("Connecting to SMTP server...")
                with smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=30) as smtp:
                    logger.info("Logging in to SMTP server...")
                    smtp.login(self.smtp_email, self.smtp_password)
                    logger.info("Sending email...")
                    smtp.send_message(msg)
                    logger.info(f"Notification email sent to {self.notification_email}")
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
            
    def _wait_for_page_load(self, timeout: int = 30):
        """ページの読み込みを待機"""
        try:
            WebDriverWait(self.driver, timeout).until(
                lambda driver: driver.execute_script('return document.readyState') == 'complete'
            )
        except TimeoutException:
            logger.warning(f"Page load timeout after {timeout} seconds")
            self._check_memory_usage()
            gc.collect()
            
    def _setup_driver(self):
        """Seleniumドライバーの初期化"""
        try:
            options = webdriver.ChromeOptions()
            options.add_argument('--headless=new')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1280,720")
            options.add_argument("--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
            
            # 自動化検出対策
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option("useAutomationExtension", False)
            
            # メモリ最適化オプション
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
            
            # さらなるステルス対策オプション
            options.add_argument("--disable-features=ChromeWhatsNewUI") # Chromeの新しいUI機能を無効化
            options.add_argument("--disable-features=ChromeMigrationWindow") # Chromeの移行ウィンドウを無効化
            options.add_argument("--disable-translate") # 翻訳機能を無効化
            options.add_argument("--hide-scrollbars") # スクロールバーを隠す
            options.add_argument("--mute-audio") # 音声をミュート
            options.add_argument("--no-default-browser-check") # デフォルトブラウザチェックを無効化
            options.add_argument("--disable-component-update") # コンポーネントアップデートを無効化
            options.add_argument("--disable-speech-api") # 音声APIを無効化
            options.add_argument("--disable-webrtc-event-logging") # WebRTCイベントログを無効化
            options.add_argument("--disable-webrtc-multiple-routes") # WebRTCの複数ルートを無効化
            options.add_argument("--disable-webrtc-stats-gathering") # WebRTC統計情報収集を無効化
            
            # メモリ制限の設定
            options.add_argument("--js-flags=--max-old-space-size=256")
            options.add_argument("--memory-pressure-off")
            options.add_argument("--disable-software-rasterizer")
            options.add_argument("--disable-dev-tools")
            options.add_argument("--disable-logging")
            options.add_argument("--log-level=3")
            options.add_argument("--silent")
            
            # 日本語表示のためのオプション
            options.add_argument("--lang=ja")
            options.add_argument("--accept-lang=ja")
            options.add_argument("--force-device-scale-factor=1")
            options.add_argument("--high-dpi-support=1")
            
            self.driver = webdriver.Chrome(options=options)
            self.wait = WebDriverWait(self.driver, 60)  # タイムアウトを60秒に短縮
            self.modal_wait = WebDriverWait(self.driver, 3)  # モーダル待機を3秒に短縮

            # Selenium-Stealthを適用
            stealth(self.driver,
                    languages=["en-US", "en"],
                    vendor="Google Inc.",
                    platform="Win32",
                    webgl_vendor="Intel Inc.",
                    renderer="Intel Iris OpenGL Engine",
                    fix_hairline=False,
                    run_on_insecure_origins=False,
                    )
            logger.info("Selenium-Stealth applied.")

            logger.info("Chrome driver initialized for Twitter bot.")
            
            # 自動化検出対策のJavaScript実行
            self._apply_stealth_script()
            
        except Exception as e:
            logger.error(f"Failed to setup Chrome driver: {str(e)}")
            # ドライバー初期化失敗時もメール通知
            self._send_error_notification("Driver Setup Failed", {'error': str(e)}, [])
            raise
            
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
            
    def _handle_security_modal(self):
        """セキュリティモーダルの処理"""
        try:
            close_button = self.modal_wait.until(EC.element_to_be_clickable((By.XPATH, '//div[@aria-label="Close"]')))
            close_button.click()
            logger.info("Security modal closed")
            self.wait.until(EC.invisibility_of_element_located((By.XPATH, '//div[@aria-label="Close"]')))
        except TimeoutException:
            logger.info("No security modal detected")
            
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def _login(self):
        """Twitterにログイン"""
        try:
            # 各種スクリーンショットのパスを保持する変数
            screenshot_initial_load = None
            screenshot_after_page_load = None
            screenshot_after_username_input = None
            screenshot_after_userid_input = None
            screenshot_after_userid_check_skipped = None
            screenshot_before_password_wait = None
            screenshot_before_password = None
            screenshot_after_password = None
            screenshot_before_login_click = None
            screenshot_after_login_click = None
            
            logger.info("Attempting to login to Twitter")
            self.driver.get('https://twitter.com/i/flow/login')
            
            # ログインページアクセス直後のスクリーンショット
            screenshot_initial_load = self._save_screenshot("login_initial_load")
            logger.info(f"Screenshot saved after initial login page load: {screenshot_initial_load}")
            self._send_debug_screenshot_email("Initial Page Load", self._collect_screenshots(screenshot_initial_load))
            
            self.driver.set_page_load_timeout(60)  # ページ読み込みタイムアウトを60秒に短縮
            
            # ページの読み込み完了を待機
            self._wait_for_page_load(timeout=60)  # ページ読み込み待機も60秒に短縮
            
            # ページ読み込み完了後のスクリーンショット
            screenshot_after_page_load = self._save_screenshot("login_after_page_load")
            logger.info(f"Screenshot saved after page load wait: {screenshot_after_page_load}")
            self._send_debug_screenshot_email("After Page Load Wait", self._collect_screenshots(screenshot_initial_load, screenshot_after_page_load))

            # 描画を促すためにbody要素をクリック
            try:
                body_element = self.driver.find_element(By.TAG_NAME, 'body')
                body_element.click()
                logger.info("Clicked body element to potentially prompt rendering.")
                time.sleep(1)  # 静的待機を1秒に短縮
            except Exception as e:
                logger.warning(f"Could not click body element: {str(e)}")

            # メモリ使用量のチェック
            self._check_memory_usage()
            
            # クッキーをクリア
            logger.info("Clearing cookies...")
            self.driver.delete_all_cookies()
            
            # ユーザー名/メールアドレス入力
            logger.info("Entering username/email...")
            try:
                initial_input = self.wait.until(EC.presence_of_element_located((By.XPATH, '//input[@autocomplete="username"] | //input[@name="text"]')))
                logger.info("Username/Email input field found.")

                initial_input.clear()
                for char in self.twitter_id:
                    initial_input.send_keys(char)
                    time.sleep(0.1)
                time.sleep(1)  # 入力後の静的待機を1秒に短縮
                initial_input.send_keys(Keys.RETURN)
                logger.info("Entered username/email and pressed RETURN.")
                
                screenshot_after_username_input = self._save_screenshot("after_username_input")
                logger.info(f"Screenshot saved after username input: {screenshot_after_username_input}")
                self._send_debug_screenshot_email("After Username Input", self._collect_screenshots(screenshot_initial_load, screenshot_after_page_load, screenshot_after_username_input))

            except TimeoutException:
                logger.error("Timeout waiting for username/email input field.")
                screenshot_path = self._save_screenshot("username_email_timeout")
                error_info = {
                    'url': self.driver.current_url if self.driver else "N/A",
                    'error': "Timeout waiting for username/email input field.",
                    'screenshot_path': screenshot_path
                }
                self._send_error_notification("Username/Email Timeout", error_info, self._collect_screenshots(screenshot_initial_load, screenshot_after_page_load, screenshot_after_username_input, screenshot_path), "twitter_bot.log")
                raise TimeoutException("Timeout waiting for username/email input field.")

            # ユーザーID確認（必要な場合）
            try:
                logger.info("Checking for user ID verification...")
                user_id_input = self.wait.until(EC.presence_of_element_located((By.XPATH, '//input[@name="text" and @data-testid="ocfEnterTextTextInput"]')))
                logger.info("User ID input field found.")

                user_id_input.clear()
                for char in self.twitter_user_id:
                    user_id_input.send_keys(char)
                    time.sleep(0.1)
                time.sleep(1)  # 入力後の静的待機を1秒に短縮
                user_id_input.send_keys(Keys.RETURN)
                logger.info("Entered user ID and pressed RETURN.")

                screenshot_after_userid_input = self._save_screenshot("after_userid_input")
                logger.info(f"Screenshot saved after user ID input: {screenshot_after_userid_input}")
                self._send_debug_screenshot_email("After User ID Input", self._collect_screenshots(screenshot_initial_load, screenshot_after_page_load, screenshot_after_username_input, screenshot_after_userid_input))

            except TimeoutException:
                logger.info("No user ID verification required or field not found within timeout.")
                screenshot_after_userid_check_skipped = self._save_screenshot("after_userid_check_skipped")
                logger.info(f"Screenshot saved after user ID check skipped: {screenshot_after_userid_check_skipped}")
                self._send_debug_screenshot_email("After User ID Check Skipped", self._collect_screenshots(screenshot_initial_load, screenshot_after_page_load, screenshot_after_username_input, screenshot_after_userid_check_skipped))

            # パスワード入力
            logger.info("Entering password...")
            
            # ユーザーID入力後の画面遷移とページ読み込み完了を待機
            self._wait_for_page_load(timeout=30)
            logger.info("Page loaded after User ID submission (if applicable).")
            time.sleep(1)  # 静的待機を1秒に短縮
            logger.info("Finished short static wait after user ID submission.")

            # エラーモーダルが表示されていないかチェックし、表示されていれば閉じる
            try:
                logger.info("Checking for error modal...")
                # エラーモーダル内のOKボタンまたは閉じるボタンを短いタイムアウトで待機
                error_ok_button = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, '//button[.//span[text()="OK"]] | //div[@aria-label="Close"]'))
                )
                logger.warning("Error modal detected. Attempting to close.")
                error_ok_button.click()
                # モーダルが閉じるまで待機
                WebDriverWait(self.driver, 5).until(
                    EC.invisibility_of_element_located((By.XPATH, '//button[.//span[text()="OK"]] | //div[@aria-label="Close"]'))
                )
                logger.info("Error modal closed successfully.")
                # モーダルを閉じた後に少し待機
                time.sleep(2)

            except TimeoutException:
                logger.info("No error modal detected or could not close within timeout.")
            except Exception as e:
                logger.error(f"An error occurred while handling error modal: {str(e)}")
                # エラーモーダルの処理中にエラーが発生した場合もスクリーンショットと通知
                screenshot_path = self._save_screenshot("error_modal_handling_error")
                error_info = {'url': self.driver.current_url if self.driver else "N/A", 'error': f"Error handling modal: {str(e)}", 'screenshot_path': screenshot_path}
                self._send_error_notification("Error Modal Handling Failed", error_info, self._collect_screenshots(screenshot_path), "twitter_bot.log")

            # エラーモーダル処理後、現在のURLを確認
            current_url_after_modal = self.driver.current_url if self.driver else "N/A"
            logger.info(f"Current URL after error modal check: {current_url_after_modal}")

            # トップページに戻されたかチェックし、その場合は早期終了
            if current_url_after_modal.rstrip('/') == 'https://x.com': # スラッシュの有無を考慮
                logger.error("Redirected to Twitter homepage after username input. Login failed, likely detected as bot.")
                # この時点のスクリーンショットとページソースをログに出力してデバッグに役立てる
                screenshot_path = self._save_screenshot("redirect_to_homepage")
                page_source = ""
                try:
                    page_source = self.driver.page_source
                except Exception as source_e:
                    logger.error(f"Failed to get page source after redirect: {str(source_e)}")

                logger.error(f"Page Source after redirect:\n{page_source[:1000]}...") # 長すぎないように一部を出力

                error_info = {
                    'url': current_url_after_modal,
                    'error': "Redirected to homepage after username/ID input. Likely bot detection.",
                    'screenshot_path': screenshot_path
                }
                # これまでのスクリーンショットと合わせてエラー通知
                self._send_error_notification("Login Redirect Failed", error_info, self._collect_screenshots(screenshot_initial_load, screenshot_after_page_load, screenshot_after_username_input, screenshot_after_userid_input if 'screenshot_after_userid_input' in locals() else (screenshot_after_userid_check_skipped if 'screenshot_after_userid_check_skipped' in locals() else None), screenshot_before_password_wait, screenshot_path), "twitter_bot.log")
                return False # ログイン失敗を示すFalseを返す

            screenshot_before_password_wait = self._save_screenshot("before_password_wait")
            logger.info(f"Screenshot saved before password input field wait: {screenshot_before_password_wait}")
            self._send_debug_screenshot_email("Before Password Wait", self._collect_screenshots(screenshot_initial_load, screenshot_after_page_load, screenshot_after_username_input, screenshot_after_userid_input if 'screenshot_after_userid_input' in locals() else (screenshot_after_userid_check_skipped if 'screenshot_after_userid_check_skipped' in locals() else None), screenshot_before_password_wait))

            try:
                # パスワード入力フィールドがクリック可能になるか、または特定の時間待機
                # Renderのワーカータイムアウトに注意しつつ、少し長めに設定
                password_input = WebDriverWait(self.driver, 90).until(
                    EC.element_to_be_clickable((By.XPATH, '//input[@name="password"]')) # ここは元のXPathに戻しました
                )
                logger.info("Password input field found and is clickable.") # ログメッセージは修正が必要です

                screenshot_before_password = self._save_screenshot("before_password_input")
                logger.info(f"Screenshot saved before password input: {screenshot_before_password}")
                self._send_debug_screenshot_email("Before Password Input", self._collect_screenshots(screenshot_initial_load, screenshot_after_page_load, screenshot_after_username_input, screenshot_after_userid_input if 'screenshot_after_userid_input' in locals() else (screenshot_after_userid_check_skipped if 'screenshot_after_userid_check_skipped' in locals() else None), screenshot_before_password_wait, screenshot_before_password))

                password_input.click()
                logger.info("Password input field clicked.")

                actions = ActionChains(self.driver)
                actions.send_keys_to_element(password_input, self.twitter_password)
                actions.perform()
                logger.info("Password entered via ActionChains.")

                screenshot_after_password = self._save_screenshot("after_password_input")
                logger.info(f"Screenshot saved after password input: {screenshot_after_password}")
                self._send_debug_screenshot_email("After Password Input", self._collect_screenshots(screenshot_initial_load, screenshot_after_page_load, screenshot_after_username_input, screenshot_after_userid_input if 'screenshot_after_userid_input' in locals() else (screenshot_after_userid_check_skipped if 'screenshot_after_userid_check_skipped' in locals() else None), screenshot_before_password_wait, screenshot_before_password, screenshot_after_password))

                time.sleep(1)  # 静的待機を1秒に短縮
                logger.info("Finished static wait after password input.")

                screenshot_before_login_click = self._save_screenshot("before_login_click")
                logger.info(f"Screenshot saved before login click: {screenshot_before_login_click}")
                self._send_debug_screenshot_email("Before Login Click", self._collect_screenshots(screenshot_initial_load, screenshot_after_page_load, screenshot_after_username_input, screenshot_after_userid_input if 'screenshot_after_userid_input' in locals() else (screenshot_after_userid_check_skipped if 'screenshot_after_userid_check_skipped' in locals() else None), screenshot_before_password_wait, screenshot_before_password, screenshot_after_password, screenshot_before_login_click))

                password_input.send_keys(Keys.RETURN)
                logger.info("Pressed RETURN on password input field (attempting login).")

                time.sleep(1)  # 静的待機を1秒に短縮
                logger.info("Finished short static wait after login attempt.")

                screenshot_after_login_click = self._save_screenshot("after_login_click")
                logger.info(f"Screenshot saved after login click: {screenshot_after_login_click}")
                self._send_debug_screenshot_email("After Login Click", self._collect_screenshots(screenshot_initial_load, screenshot_after_page_load, screenshot_after_username_input, screenshot_after_userid_input if 'screenshot_after_userid_input' in locals() else (screenshot_after_userid_check_skipped if 'screenshot_after_userid_check_skipped' in locals() else None), screenshot_before_password_wait, screenshot_before_password, screenshot_after_password, screenshot_before_login_click, screenshot_after_login_click))

            except TimeoutException:
                logger.error("Timeout waiting for password input field.")
                screenshot_path = self._save_screenshot("password_input_timeout")
                # エラー時のURLとページソースもログに出力
                current_url = self.driver.current_url if self.driver else "N/A"
                page_source = ""
                try:
                    page_source = self.driver.page_source
                except Exception as source_e:
                    logger.error(f"Failed to get page source: {str(source_e)}")
                    
                logger.error(f"Current URL: {current_url}")
                logger.error(f"Page Source:\n{page_source[:1000]}...") # ソースが長い可能性があるので最初の1000文字程度に制限

                error_info = {
                    'url': current_url,
                    'error': "Timeout waiting for password input field.",
                    'screenshot_path': screenshot_path
                }
                self._send_error_notification("Password Input Timeout", error_info, self._collect_screenshots(screenshot_initial_load, screenshot_after_page_load, screenshot_after_username_input, screenshot_after_userid_input if 'screenshot_after_userid_input' in locals() else (screenshot_after_userid_check_skipped if 'screenshot_after_userid_check_skipped' in locals() else None), screenshot_before_password_wait, screenshot_before_password, screenshot_after_password, screenshot_before_login_click, screenshot_after_login_click, screenshot_path), "twitter_bot.log")
                raise TimeoutException("Timeout waiting for password input field.")

            # ログイン完了の待機
            logger.info("Waiting for login completion or confirmation code screen...")
            login_successful = False
            try:
                # 認証コード入力フィールドがクリック可能になるか待機
                logger.info("Waiting for confirmation code input field to be clickable...")
                confirmation_code_input_field = self.wait.until(
                    EC.element_to_be_clickable((By.XPATH, '//input[@name="email_code"] | //input[@autocomplete="one-time-code"] | //input[@data-testid="ocfEnterTextTextInput"]'))
                )
                logger.info("Confirmation code input field found and is clickable.")

                # 認証コード処理
                confirmation_code = self._get_twitter_confirmation_code()
                if confirmation_code:
                    logger.info(f"Retrieved confirmation code: {confirmation_code}")
                    # 認証コード入力処理
                    # ... 既存の認証コード処理コード ...

            except TimeoutException:
                # 認証コード入力フィールドが見つからなかった場合、ログイン成功要素が出現するか待機
                logger.info("Confirmation code input field not found within timeout. Waiting for standard login completion elements...")
                try:
                    self.wait.until(
                        EC.presence_of_element_located((By.XPATH, '//div[@data-testid="tweetTextarea_0"] | //div[@aria-label="Home timeline"] | //a[@data-testid="AppTabBar_Home_Link"]'))
                    )
                    logger.info("Standard login completion elements found.")
                    login_successful = True
                except TimeoutException:
                    logger.error("Timeout waiting for standard login completion elements.")
                    raise TimeoutException("Timeout waiting for standard login completion elements.")

            return login_successful

        except Exception as e:
            logger.error(f"Login failed: {str(e)}")
            self._check_memory_usage()
            screenshot_path = self._save_screenshot("login_general_error")
            if screenshot_path:
                logger.info(f"Login error screenshot saved: {screenshot_path}")
            current_url = self.driver.current_url if self.driver else "N/A"
            logger.error(f"Login failed at URL: {current_url}")

            error_info = {
                'url': current_url,
                'error': str(e),
                'screenshot_path': screenshot_path
            }
            self._send_error_notification("Login Failed", error_info, self._collect_screenshots(screenshot_initial_load, screenshot_after_page_load, screenshot_after_username_input, screenshot_after_userid_input if 'screenshot_after_userid_input' in locals() else (screenshot_after_userid_check_skipped if 'screenshot_after_userid_check_skipped' in locals() else None), screenshot_before_password_wait, screenshot_before_password, screenshot_after_password, screenshot_before_login_click, screenshot_after_login_click, screenshot_path), "twitter_bot.log")

            raise

    # デバッグ用：各ステップのスクリーンショットをメール送信するヘルパー関数を追加
    def _send_debug_screenshot_email(self, step_name: str, screenshot_paths: list[str]):
        """デバッグ用に特定のステップ完了時のスクリーンショットをメール送信"""
        # デバッグモードが有効な場合のみメール送信
        if not os.getenv("DEBUG_MODE", "false").lower() == "true":
            return
        
        if not screenshot_paths:
            logger.warning(f"No screenshots to send for debug step: {step_name}")
            return

        # 最新のスクリーンショットのみを送信
        latest_screenshot = screenshot_paths[-1]
        subject = f'Twitter Bot Debug Screenshot: {step_name}'
        body = f'{step_name} 完了時の画面スクリーンショットです。'
        self._send_notification_email(subject, body, [latest_screenshot])
        logger.info(f"Debug screenshot email sent for step: {step_name}")

    # スクリーンショットパスをリストにまとめるヘルパー関数
    def _collect_screenshots(self, *args):
        """Noneでないスクリーンショットパスをリストにして返す"""
        return [path for path in args if path]

    # エラー通知用のラッパーメソッド
    def _send_error_notification(self, error_type: str, error_info: Dict[str, Any], screenshot_paths: list[str], log_file_path: Optional[str] = None):
        """エラー通知メールを送信するためのラッパー"""
        subject = f'Twitter Bot Error: {error_type}'
        body = f"""
エラーが発生しました。

エラータイプ: {error_type}
発生時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
URL: {error_info.get('url', 'N/A')}
エラー詳細: {error_info.get('error', 'N/A')}
メモリ使用量: {psutil.Process(os.getpid()).memory_percent():.1f}%
"""
        # 渡されたスクリーンショットパスをそのまま使用
        self._send_notification_email(subject, body, screenshot_paths, log_file_path)

    # GmailからTwitter認証コードを取得する関数を追加
    def _get_twitter_confirmation_code(self) -> Optional[str]:
        """Gmailから最新のTwitter認証コードメールを取得し、コードを抽出する"""
        import imaplib
        import email
        import re

        gmail_user = os.getenv("GMAIL_ADDRESS") # 環境変数からGmailアドレスを取得
        gmail_app_password = os.getenv("GMAIL_APP_PASSWORD") # 環境変数からGmailアプリパスワードを取得

        if not all([gmail_user, gmail_app_password]):
            logger.warning("GMAIL_ADDRESS or GMAIL_APP_PASSWORD not set. Cannot retrieve confirmation code.")
            return None

        confirmation_code = None
        try:
            logger.info(f"Attempting to connect to Gmail IMAP server for user: {gmail_user}")
            # IMAP_SSLでGmailに接続
            mail = imaplib.IMAP4_SSL('imap.gmail.com')
            # ログイン
            mail.login(gmail_user, gmail_app_password)
            logger.info("Logged in to Gmail IMAP server.")

            # 受信トレイを選択
            mail.select('inbox')
            logger.info("Selected INBOX.")

            # Twitterからの最新の認証コードメールを検索
            # 送信元アドレスと件名でフィルタリング
            # Twitterの認証コードメールの件名や送信元は変わる可能性があるため、適宜調整が必要
            status, email_ids = mail.search(None,
                                             '(FROM "info@x.com" SUBJECT "Your X confirmation code is ")')

            if status == 'OK' and email_ids[0]:
                # 最新のメールIDを取得
                latest_email_id = email_ids[0].split()[-1]
                logger.info(f"Found latest Twitter confirmation email with ID: {latest_email_id}")

                # メールを取得
                status, msg_data = mail.fetch(latest_email_id, '(RFC822)')
                if status == 'OK':
                    msg = email.message_from_bytes(msg_data[0][1])
                    logger.info(f"Fetched email with subject: {msg['Subject']}")

                    # メール本文から認証コードを抽出
                    if msg.is_multipart():
                        for part in msg.walk():
                            ctype = part.get_content_type()
                            cdisp = str(part.get('Content-Disposition'))

                            # text/plain または text/html のパートを取得
                            if ctype == 'text/plain' and 'attachment' not in cdisp:
                                body = part.get_payload(decode=True).decode()
                                # 本文から認証コード（例: 6桁の数字など、Twitterのコード形式に合わせる）を正規表現で抽出
                                # 認証コードの形式に合わせて正規表現を調整してください
                                # 件名または本文から "is " または ">" に続いて出現する英数字の連続を抽出
                                match = re.search(r'is ([a-zA-Z0-9]+)', body) # 例: "is 123ABC" の形式
                                if match:
                                    confirmation_code = match.group(1)
                                    logger.info(f"Extracted confirmation code from plain text body: {confirmation_code}")
                                    break # コードが見つかったらループを抜ける

                            elif ctype == 'text/html' and 'attachment' not in cdisp:
                                body = part.get_payload(decode=True).decode()
                                # HTML本文から認証コードを抽出
                                # 認証コードの形式に合わせて正規表現を調整してください
                                # 件名または本文から ">" に続いて出現する英数字の連続を抽出
                                match = re.search(r'>([a-zA-Z0-9]+)<', body) # 例: <div>123ABC</div> の形式
                                if match:
                                    confirmation_code = match.group(1)
                                    logger.info(f"Extracted confirmation code from HTML body: {confirmation_code}")
                                    break # コードが見つかったらループを抜ける

                    # TODO: メールを既読にするなど、必要に応じて処理を追加
                    # mail.store(latest_email_id, '+FLAGS', '\\Seen')

                else:
                    logger.error(f"Failed to fetch email with ID {latest_email_id}. Status: {status}")

            else:
                logger.warning("No Twitter confirmation email found in INBOX.")

        except imaplib.IMAP4.error as e:
            logger.error(f"IMAP error occurred: {str(e)}")
        except Exception as e:
            logger.error(f"An error occurred while retrieving confirmation code from email: {str(e)}")
        finally:
            # 接続を閉じる
            if 'mail' in locals() and mail:
                try:
                    mail.logout()
                    logger.info("Logged out from Gmail IMAP server.")
                except Exception as e:
                     logger.error(f"Error during IMAP logout: {str(e)}")

        return confirmation_code

    def post_tweet(self, title: str, url: str) -> bool:
        """ツイートを投稿する"""
        try:
            logger.info(f"Starting tweet posting process for title: {title}")
            # _loginメソッドは内部で_setup_driverを呼び出し、ログインに失敗した場合は例外を発生させます。
            # 成功した場合のみ、以下の処理に進みます。
            # post_tweet内で_setup_driverを呼ぶと、リトライ時に毎回新しいドライバーが起動してしまうため、
            # _loginメソッドのretryデコレータがドライバーの再利用を前提としていない挙動になります。
            # _loginメソッドの前に_setup_driverを呼ぶように修正します。
            self._setup_driver()
            logger.info("Driver setup complete in post_tweet")

            # ログインを試行し、成功した場合のみ以降の処理に進む
            if not self._login():
                logger.error("Login failed. Aborting tweet posting process.")
                return False # ログイン失敗時はFalseを返して終了

            # ツイート作成画面を開く
            logger.info("Opening tweet composition screen...")
            # ログイン後の画面が安定するまで待機
            time.sleep(5) # ログイン後の静的待機を追加

            try:
                post_button = self.wait.until(EC.element_to_be_clickable((By.XPATH, '//a[@aria-label="Post"]')))
                post_button.click()
            except TimeoutException:
                logger.error("Timeout waiting for tweet post button.")
                screenshot_path = self._save_screenshot("post_button_timeout")
                error_info = {'url': self.driver.current_url if self.driver else "N/A", 'error': "Timeout waiting for tweet post button.", 'screenshot_path': screenshot_path}
                self._send_error_notification("Tweet Post Button Timeout", error_info, [screenshot_path] if screenshot_path else [], "twitter_bot.log")
                raise TimeoutException("Timeout waiting for tweet post button.")
            except NoSuchElementException:
                logger.error("Tweet post button not found.")
                screenshot_path = self._save_screenshot("post_button_not_found")
                error_info = {'url': self.driver.current_url if self.driver else "N/A", 'error': "Tweet post button not found.", 'screenshot_path': screenshot_path}
                self._send_error_notification("Tweet Post Button Not Found", error_info, [screenshot_path] if screenshot_path else [], "twitter_bot.log")
                raise NoSuchElementException("Tweet post button not found.")
            except Exception as e:
                logger.error(f"Error clicking tweet post button: {str(e)}")
                screenshot_path = self._save_screenshot("post_button_error")
                error_info = {'url': self.driver.current_url if self.driver else "N/A", 'error': str(e), 'screenshot_path': screenshot_path}
                self._send_error_notification("Tweet Post Button Error", error_info, [screenshot_path] if screenshot_path else [], "twitter_bot.log")
                raise

            # ツイート内容の入力
            logger.info("Entering tweet content...")
            # ツイート作成モーダルが表示されるのを待機
            time.sleep(3) # モーダル表示の静的待機を追加

            try:
                tweet_box = self.wait.until(EC.presence_of_element_located((By.XPATH, '//div[@data-testid="tweetTextarea_0"]')))
                tweet_content = f"{title}\n{url}"
                tweet_box.send_keys(tweet_content)
                time.sleep(2)
            except TimeoutException:
                logger.error("Timeout waiting for tweet text area.")
                screenshot_path = self._save_screenshot("tweet_area_timeout")
                error_info = {'url': self.driver.current_url if self.driver else "N/A", 'error': "Timeout waiting for tweet text area.", 'screenshot_path': screenshot_path}
                self._send_error_notification("Tweet Area Timeout", error_info, [screenshot_path] if screenshot_path else [], "twitter_bot.log")
                raise TimeoutException("Timeout waiting for tweet text area.")
            except NoSuchElementException:
                logger.error("Tweet text area not found.")
                screenshot_path = self._save_screenshot("tweet_area_not_found")
                error_info = {'url': self.driver.current_url if self.driver else "N/A", 'error': "Tweet text area not found.", 'screenshot_path': screenshot_path}
                self._send_error_notification("Tweet Area Not Found", error_info, [screenshot_path] if screenshot_path else [], "twitter_bot.log")
                raise NoSuchElementException("Tweet text area not found.")
            except Exception as e:
                logger.error(f"Error entering tweet content: {str(e)}")
                screenshot_path = self._save_screenshot("tweet_content_error")
                error_info = {'url': self.driver.current_url if self.driver else "N/A", 'error': str(e), 'screenshot_path': screenshot_path}
                self._send_error_notification("Tweet Content Error", error_info, [screenshot_path] if screenshot_path else [], "twitter_bot.log")
                raise

            # 投稿ボタンのクリック
            logger.info("Clicking post button...")
            try:
                # ツイート作成モーダル内の投稿ボタンを対象とする
                tweet_button = self.wait.until(EC.element_to_be_clickable((By.XPATH, '//div[@data-testid="tweetComposer"]//button[@data-testid="tweetButton"]')))
                tweet_button.click()
            except TimeoutException:
                logger.error("Timeout waiting for final tweet button.")
                screenshot_path = self._save_screenshot("final_tweet_button_timeout")
                error_info = {'url': self.driver.current_url if self.driver else "N/A", 'error': "Timeout waiting for final tweet button.", 'screenshot_path': screenshot_path}
                self._send_error_notification("Final Tweet Button Timeout", error_info, [screenshot_path] if screenshot_path else [], "twitter_bot.log")
                raise TimeoutException("Timeout waiting for final tweet button.")
            except NoSuchElementException:
                logger.error("Final tweet button not found.")
                screenshot_path = self._save_screenshot("final_tweet_button_not_found")
                error_info = {'url': self.driver.current_url if self.driver else "N/A", 'error': "Final tweet button not found.", 'screenshot_path': screenshot_path}
                self._send_error_notification("Final Tweet Button Not Found", error_info, [screenshot_path] if screenshot_path else [], "twitter_bot.log")
                raise NoSuchElementException("Final tweet button not found.")
            except Exception as e:
                logger.error(f"Error clicking final tweet button: {str(e)}")
                screenshot_path = self._save_screenshot("final_tweet_button_error")
                error_info = {'url': self.driver.current_url if self.driver else "N/A", 'error': str(e), 'screenshot_path': screenshot_path}
                self._send_error_notification("Final Tweet Button Error", error_info, [screenshot_path] if screenshot_path else [], "twitter_bot.log")
                raise

            # 投稿完了の待機 (成功メッセージやツイートが表示されるのを待つなど、より具体的な条件にすることも検討)
            logger.info("Waiting for tweet completion...")
            time.sleep(10) # 一旦静的な待機
            # TODO: ツイートが成功したことを示す要素や画面遷移を待つ条件を追加
            logger.info("Tweet posting process finished (Success confirmation might be needed).")

            # 正常終了時も通知メールを送信
            success_info = {
                 'url': self.driver.current_url if self.driver else "N/A",
                 'title': title,
                 'memory_usage': psutil.Process(os.getpid()).memory_percent()
            }
            self._send_notification_email('Twitter Post Success', 'ツイート投稿が正常に完了しました。', [], "twitter_bot.log")

            return True

        except Exception as e:
            logger.error(f"Failed to post tweet. Error: {str(e)}")
            self._check_memory_usage()
            screenshot_path = self._save_screenshot("post_tweet_error")
            if screenshot_path:
                logger.info(f"Error screenshot saved: {screenshot_path}")
            current_url = self.driver.current_url if self.driver else "N/A"
            logger.error(f"Tweet post failed at URL: {current_url}")

            # 投稿失敗時のメール通知
            error_info = {
                'url': current_url,
                'error': str(e),
                'screenshot_path': screenshot_path
            }
            self._send_error_notification("Tweet Post Failed", error_info, [screenshot_path] if screenshot_path else [], "twitter_bot.log")

            return False

        finally:
            self.cleanup()

if __name__ == "__main__":
    test_title = os.getenv("TEST_TWEET_TITLE", "テスト投稿タイトル")
    test_url = os.getenv("TEST_TWEET_URL", "https://example.com")

    bot = TwitterBot()
    success = bot.post_tweet(test_title, test_url)

    if success:
        logger.info("ツイート投稿処理が成功しました。")
    else:
        logger.error("ツイート投稿処理が失敗しました。")