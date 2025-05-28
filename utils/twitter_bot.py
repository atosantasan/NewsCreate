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
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
        
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=options)
        self.wait = WebDriverWait(self.driver, 20)
        self.modal_wait = WebDriverWait(self.driver, 5)
        
    def _handle_security_modal(self):
        """セキュリティモーダルの処理"""
        try:
            close_button = self.modal_wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'div[aria-label="Close"]')))
            close_button.click()
            logger.info("Security modal closed")
            self.wait.until(EC.invisibility_of_element_located((By.CSS_SELECTOR, 'div[aria-label="Close"]')))
        except TimeoutException:
            logger.info("No security modal detected")
            
    def _login(self):
        """Twitterにログイン"""
        try:
            logger.info("Attempting to login to Twitter")
            self.driver.get('https://twitter.com/i/flow/login')
            
            # ユーザー名/メールアドレス入力
            initial_input = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input[autocomplete="username"], input[name="text"]')))
            initial_input.send_keys(self.twitter_id)
            initial_input.send_keys(Keys.RETURN)
            
            # ユーザーID確認（必要な場合）
            try:
                user_id_input = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input[name="text"][data-testid="ocfEnterTextTextInput"]')))
                user_id_input.send_keys(self.twitter_user_id)
                user_id_input.send_keys(Keys.RETURN)
                logger.info("User ID verification completed")
            except TimeoutException:
                logger.info("No user ID verification required")
                
            # パスワード入力
            password_input = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type="password"], input[name="password"]')))
            password_input.send_keys(self.twitter_password)
            password_input.send_keys(Keys.RETURN)
            
            # ログイン完了の待機
            self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'div[data-testid="tweetTextarea_0"], div[aria-label="What\'s happening?"]')))
            logger.info("Successfully logged in to Twitter")
            
        except Exception as e:
            logger.error(f"Login failed: {str(e)}")
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
            self._handle_security_modal()
            self._login()
            
            # ツイート作成画面を開く
            post_button = self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'a[aria-label="Post"]')))
            post_button.click()
            
            # ツイート内容の入力
            tweet_box = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'div[data-testid="tweetTextarea_0"]')))
            tweet_content = f"{title}\n{url}"
            tweet_box.send_keys(tweet_content)
            
            # 投稿ボタンのクリック
            tweet_button = self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[data-testid="tweetButton"], div[data-testid="tweetButtonInline"]')))
            tweet_button.click()
            
            # 投稿完了の待機
            time.sleep(5)
            logger.info("Tweet posted successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to post tweet: {str(e)}")
            if self.driver:
                self.driver.save_screenshot("twitter_error_screenshot.png")
                logger.info("Error screenshot saved as twitter_error_screenshot.png")
            return False
            
        finally:
            if self.driver:
                self.driver.quit()

if __name__ == "__main__":
    bot = TwitterBot()
    bot.post_tweet("ようやくできる", "AI情報の投稿")