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
from typing import Optional
from dotenv import load_dotenv
import gc
import signal
import sys
import psutil
from tenacity import retry, stop_after_attempt, wait_exponential
import tempfile
from datetime import datetime

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
        
        if not all([self.twitter_id, self.twitter_user_id, self.twitter_password]):
            raise ValueError("TWITTER_ID, TWITTER_USER_ID, and TWITTER_PASSWORD are required")
            
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
            self.wait = WebDriverWait(self.driver, 40)
            self.modal_wait = WebDriverWait(self.driver, 5)
            logger.info("Chrome driver initialized for Twitter bot.")
            
            # 自動化検出対策のJavaScript実行
            self._apply_stealth_script()
            
        except Exception as e:
            logger.error(f"Failed to setup Chrome driver: {str(e)}")
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
            logger.info("Attempting to login to Twitter")
            self._setup_driver()
            self.driver.get('https://twitter.com/i/flow/login')
            self.driver.set_page_load_timeout(60)
            
            # ページの読み込み完了を待機
            self._wait_for_page_load(timeout=60)
            
            # メモリ使用量のチェック
            self._check_memory_usage()
            
            # クッキーをクリア
            logger.info("Clearing cookies...")
            self.driver.delete_all_cookies()
            
            # ユーザー名/メールアドレス入力
            logger.info("Entering username/email...")
            initial_input = self.wait.until(EC.presence_of_element_located((By.XPATH, '//input[@autocomplete="username"] | //input[@name="text"]')))
            initial_input.clear()
            for char in self.twitter_id:
                initial_input.send_keys(char)
                time.sleep(0.1)
            time.sleep(2)
            initial_input.send_keys(Keys.RETURN)
            
            # ユーザーID確認（必要な場合）
            try:
                logger.info("Checking for user ID verification...")
                user_id_input = self.wait.until(EC.presence_of_element_located((By.XPATH, '//input[@name="text" and @data-testid="ocfEnterTextTextInput"]')))
                user_id_input.clear()
                for char in self.twitter_user_id:
                    user_id_input.send_keys(char)
                    time.sleep(0.1)
                time.sleep(2)
                user_id_input.send_keys(Keys.RETURN)
                logger.info("User ID verification completed")
            except TimeoutException:
                logger.info("No user ID verification required")
                
            # パスワード入力
            logger.info("Entering password...")
            password_input = self.wait.until(EC.presence_of_element_located((By.XPATH, '//input[@type="password"] | //input[@name="password"]')))
            password_input.clear()
            for char in self.twitter_password:
                password_input.send_keys(char)
                time.sleep(0.1)
            time.sleep(2)
            password_input.send_keys(Keys.RETURN)
            
            # ログイン完了の待機
            logger.info("Waiting for login completion...")
            try:
                # ツイート入力エリアまたはホームボタンの出現を待機
                self.wait.until(
                    EC.presence_of_element_located((By.XPATH, '//div[@data-testid="tweetTextarea_0"] | //div[@aria-label="Home timeline"] | //a[@data-testid="AppTabBar_Home_Link"]'))
                )
                logger.info("Successfully logged in to Twitter")
            except TimeoutException:
                logger.error("Timeout waiting for login completion elements.")
                raise TimeoutException("Timeout waiting for login completion elements.") # タイムアウト時に例外を再発生
            
        except Exception as e:
            logger.error(f"Login failed: {str(e)}")
            self._check_memory_usage()
            screenshot_path = self._save_screenshot("login_error")
            if screenshot_path:
                logger.info(f"Login error screenshot saved: {screenshot_path}")
            # エラー時の詳細情報を追加
            current_url = self.driver.current_url if self.driver else "N/A"
            page_source = self.driver.page_source if self.driver else "N/A"
            logger.error(f"Login failed at URL: {current_url}")
            # ページのソースは長くなる可能性があるため、必要に応じてコメントアウトや一部表示に調整
            # logger.error(f"Page source: {page_source[:500]}...") 
            raise # 例外を再発生させて、リトライ処理に委ねる
            
    def post_tweet(self, title: str, url: str) -> bool:
        """ツイートを投稿する"""
        try:
            logger.info(f"Starting tweet posting process for title: {title}")
            # _loginメソッドは内部で_setup_driverを呼び出し、ログインに失敗した場合は例外を発生させます。
            # 成功した場合のみ、以下の処理に進みます。
            self._login()
            
            # ツイート作成画面を開く
            logger.info("Opening tweet composition screen...")
            try:
                post_button = self.wait.until(EC.element_to_be_clickable((By.XPATH, '//a[@aria-label="Post"]')))
                post_button.click()
            except TimeoutException:
                logger.error("Timeout waiting for tweet post button.")
                self._save_screenshot("post_button_timeout")
                raise TimeoutException("Timeout waiting for tweet post button.")
            except NoSuchElementException:
                logger.error("Tweet post button not found.")
                self._save_screenshot("post_button_not_found")
                raise NoSuchElementException("Tweet post button not found.")
            except Exception as e:
                logger.error(f"Error clicking tweet post button: {str(e)}")
                self._save_screenshot("post_button_error")
                raise
            
            # ツイート内容の入力
            logger.info("Entering tweet content...")
            try:
                tweet_box = self.wait.until(EC.presence_of_element_located((By.XPATH, '//div[@data-testid="tweetTextarea_0"]')))
                tweet_content = f"{title}\n{url}"
                tweet_box.send_keys(tweet_content)
                time.sleep(2)
            except TimeoutException:
                logger.error("Timeout waiting for tweet text area.")
                self._save_screenshot("tweet_area_timeout")
                raise TimeoutException("Timeout waiting for tweet text area.")
            except NoSuchElementException:
                logger.error("Tweet text area not found.")
                self._save_screenshot("tweet_area_not_found")
                raise NoSuchElementException("Tweet text area not found.")
            except Exception as e:
                logger.error(f"Error entering tweet content: {str(e)}")
                self._save_screenshot("tweet_content_error")
                raise
            
            # 投稿ボタンのクリック
            logger.info("Clicking post button...")
            try:
                # ツイート作成モーダル内の投稿ボタンを対象とする
                tweet_button = self.wait.until(EC.element_to_be_clickable((By.XPATH, '//div[@data-testid="tweetComposer"]//button[@data-testid="tweetButton"]')))
                tweet_button.click()
            except TimeoutException:
                logger.error("Timeout waiting for final tweet button.")
                self._save_screenshot("final_tweet_button_timeout")
                raise TimeoutException("Timeout waiting for final tweet button.")
            except NoSuchElementException:
                logger.error("Final tweet button not found.")
                self._save_screenshot("final_tweet_button_not_found")
                raise NoSuchElementException("Final tweet button not found.")
            except Exception as e:
                logger.error(f"Error clicking final tweet button: {str(e)}")
                self._save_screenshot("final_tweet_button_error")
                raise
            
            # 投稿完了の待機 (成功メッセージやツイートが表示されるのを待つなど、より具体的な条件にすることも検討)
            logger.info("Waiting for tweet completion...")
            time.sleep(10) # 一旦静的な待機
            # TODO: ツイートが成功したことを示す要素や画面遷移を待つ条件を追加
            logger.info("Tweet posting process finished (Success confirmation might be needed).")
            return True
            
        except Exception as e:
            logger.error(f"Failed to post tweet: {str(e)}")
            self._check_memory_usage()
            screenshot_path = self._save_screenshot("post_tweet_error") # エラータイプ名を変更
            if screenshot_path:
                logger.info(f"Error screenshot saved: {screenshot_path}")
            # エラー時の詳細情報を追加
            current_url = self.driver.current_url if self.driver else "N/A"
            page_source = self.driver.page_source if self.driver else "N/A"
            logger.error(f"Tweet post failed at URL: {current_url}")
            # logger.error(f"Page source: {page_source[:500]}...")
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