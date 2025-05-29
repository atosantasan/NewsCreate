from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager
import time
import os
import logging
from typing import Optional
from dotenv import load_dotenv

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
        
    def _setup_driver(self):
        """Seleniumドライバーの初期化"""
        options = webdriver.ChromeOptions()
        options.add_argument('--headless=new') # 新しいheadlessモード
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument("--disable-gpu") # GPUの無効化 (note_post.pyに倣う)
        options.add_argument("--window-size=1280,720") # ウィンドウサイズ (note_post.pyに倣う)

        # 自動化検出対策 (note_post.pyに倣う)
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        # Renderなどのサーバー環境でChromeバイナリを指定する代わりに、
        # WebDriverManagerに任せるか、Render環境のデフォルトパスに期待します。
        # options.binary_location = '/usr/bin/google-chrome' # この行を削除

        service = Service(ChromeDriverManager().install()) # WebDriverManagerを使用
        self.driver = webdriver.Chrome(service=service, options=options)
        self.wait = WebDriverWait(self.driver, 40)
        self.modal_wait = WebDriverWait(self.driver, 5)
        logger.info("Chrome driver initialized for Twitter bot.") # ログ変更
        
    def _handle_security_modal(self):
        """セキュリティモーダルの処理"""
        try:
            close_button = self.modal_wait.until(EC.element_to_be_clickable((By.XPATH, '//div[@aria-label="Close"]')))
            close_button.click()
            logger.info("Security modal closed")
            self.wait.until(EC.invisibility_of_element_located((By.XPATH, '//div[@aria-label="Close"]')))
        except TimeoutException:
            logger.info("No security modal detected")
            
    def _login(self):
        """Twitterにログイン"""
        try:
            logger.info("Attempting to login to Twitter")
            self._setup_driver()
            self.driver.get('https://twitter.com/i/flow/login')
            
            # ユーザー名/メールアドレス入力
            initial_input = self.wait.until(EC.presence_of_element_located((By.XPATH, '//input[@autocomplete="username"] | //input[@name="text"]')))
            initial_input.send_keys(self.twitter_id)
            initial_input.send_keys(Keys.RETURN)
            
            # ユーザーID確認（必要な場合）
            try:
                user_id_input = self.wait.until(EC.presence_of_element_located((By.XPATH, '//input[@name="text" and @data-testid="ocfEnterTextTextInput"]')))
                user_id_input.send_keys(self.twitter_user_id)
                user_id_input.send_keys(Keys.RETURN)
                logger.info("User ID verification completed")
            except TimeoutException:
                logger.info("No user ID verification required")
                
            # パスワード入力
            password_input = self.wait.until(EC.presence_of_element_located((By.XPATH, '//input[@type="password"] | //input[@name="password"]')))
            password_input.send_keys(self.twitter_password)
            password_input.send_keys(Keys.RETURN)
            
            # ログイン完了の待機
            self.wait.until(EC.presence_of_element_located((By.XPATH, '//div[@data-testid="tweetTextarea_0"] | //div[@aria-label="What\'s happening?"]')))
            logger.info("Successfully logged in to Twitter")
            
        except Exception as e:
            logger.error(f"Login failed: {str(e)}")
            if self.driver:
                self.driver.save_screenshot("twitter_login_error_screenshot.png")
                logger.info("Login error screenshot saved as twitter_login_error_screenshot.png")
            raise
            
    def post_tweet(self, title: str, url: str) -> bool:
        """
        ツイートを投稿する
        
        Args:
            title (str): ツイートのタイトル
            url (str): ツイートに含めるURL
            
        Returns:
            bool: 投稿成功時はTrue、失敗時はFalse
        """
        try:
            logger.info(f"Starting tweet posting process for title: {title}")
            self._setup_driver()
            self._login()
            
            # ツイート作成画面を開く
            post_button = self.wait.until(EC.element_to_be_clickable((By.XPATH, '//a[@aria-label="Post"]')))
            post_button.click()
            
            # ツイート内容の入力
            tweet_box = self.wait.until(EC.presence_of_element_located((By.XPATH, '//div[@data-testid="tweetTextarea_0"]')))
            tweet_content = f"{title}\n{url}"
            tweet_box.send_keys(tweet_content)
            
            # 投稿ボタンのクリック
            tweet_button = self.wait.until(EC.element_to_be_clickable((By.XPATH, '//button[@data-testid="tweetButton"] | //div[@data-testid="tweetButtonInline"]')))
            tweet_button.click()
            
            # 投稿完了の待機
            time.sleep(10)
            logger.info("Tweet posted successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to post tweet: {str(e)}")
            if self.driver:
                self.driver.save_screenshot("twitter_post_error_screenshot.png")
                logger.info("Error screenshot saved as twitter_post_error_screenshot.png")
            return False
            
        finally:
            if self.driver:
                self.driver.quit()
                logger.info("Driver quit.")

if __name__ == "__main__":
    # 環境変数からタイトルとURLを取得するか、デフォルト値を設定
    test_title = os.getenv("TEST_TWEET_TITLE", "テスト投稿タイトル")
    test_url = os.getenv("TEST_TWEET_URL", "https://example.com")

    bot = TwitterBot()
    success = bot.post_tweet(test_title, test_url)

    if success:
        logger.info("ツイート投稿処理が成功しました。")
    else:
        logger.error("ツイート投稿処理が失敗しました。")