import google.generativeai as genai
import os
from ..utils.logger import get_logger

logger = get_logger(__name__)

class GeminiWriter:
    def __init__(self):
        self.api_key = os.getenv('GEMINI_API_KEY')
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not set")
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel('gemini-pro')
    
    def generate_article(self, title, content):
        """
        記事を生成します。
        
        Args:
            title (str): 記事のタイトル
            content (str): 元となるコンテンツ
            
        Returns:
            str: 生成された記事
        """
        try:
            prompt = f"""
            以下のタイトルとコンテンツを元に、記事を生成してください。
            
            タイトル: {title}
            
            元コンテンツ:
            {content}
            
            以下の形式で記事を生成してください：
            1. 導入部（背景説明）
            2. 本文（詳細な説明）
            3. 結論（まとめ）
            """
            
            response = self.model.generate_content(prompt)
            generated_article = response.text
            
            logger.info(f"記事の生成に成功しました: {title}")
            return generated_article
            
        except Exception as e:
            logger.error(f"記事の生成中にエラーが発生しました: {str(e)}")
            raise
