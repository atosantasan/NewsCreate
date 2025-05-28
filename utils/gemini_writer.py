import google.generativeai as genai
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class GeminiWriter:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is required")
        
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel("gemini-2.0-flash")
        
    def generate_article(self, title: str, content: str) -> str:
        """
        ニュース情報から記事を生成する
        
        Args:
            title (str): ニュースのタイトル
            content (str): ニュースの本文
            
        Returns:
            str: 生成された記事本文
        """
        prompt = f"""
        以下のニュース情報をもとに、Note投稿に適した自然な日本語の記事を作成してください。

        # 制約条件：
        - 読みやすく、簡潔に。
        - 序文、中盤、結論を含む構成。
        - タイトルに合った内容を維持する。

        # ニュースタイトル：
        {title}

        # ニュース本文：
        {content}

        # 出力形式：
        Noteに投稿する用のテキストのみ出力してください。
        """

        try:
            logger.info(f"Generating article for title: {title}")
            response = self.model.generate_content(prompt)
            logger.info("Article generated successfully")
            return response.text
        except Exception as e:
            logger.error(f"Failed to generate article: {str(e)}")
            raise
