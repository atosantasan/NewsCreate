# NewsCreate

ニュース記事の自動生成と投稿システム

## 機能

- RSSフィードからのニュース取得
- Gemini AIによる記事生成
- Noteへの記事投稿
- Twitterへの投稿

## セットアップ

1. リポジトリのクローン
```bash
git clone [repository-url]
cd NewsCreate
```

2. 仮想環境の作成と有効化
```bash
python -m venv venv
source venv/bin/activate  # Linuxの場合
# または
.\venv\Scripts\activate  # Windowsの場合
```

3. 依存パッケージのインストール
```bash
pip install -r requirements.txt
```

4. 環境変数の設定
```bash
cp .env.example .env
# .envファイルを編集して必要な設定を入力
```

5. アプリケーションの起動
```bash
flask run
```

## APIエンドポイント

### ニュース取得
- `GET /api/v1/fetch_news`
  - RSSフィードからニュース記事を取得

### 記事生成
- `POST /api/v1/generate`
  - ニュース情報から記事を生成
  - リクエストボディ: `{"title": "タイトル", "content": "本文"}`

### Note投稿
- `POST /api/v1/post_note`
  - 記事をNoteに投稿
  - リクエストボディ: `{"title": "タイトル", "content": "本文"}`

### Twitter投稿
- `POST /api/v1/post_twitter`
  - ツイートを投稿
  - リクエストボディ: `{"title": "タイトル", "url": "URL"}`

## 開発環境

- Python 3.8以上
- Flask 3.0.2
- Google Generative AI
- Selenium
- Tweepy

## ライセンス

MIT

# AIニュース自動投稿ボット

## 概要
このプロジェクトは、Webクローリングで最新のAI関連ニュースを収集し、Anthropic Gemini APIで記事を生成して  
noteに自動投稿し、さらにTwitterへ共有する完全自動化ニュース投稿ボットです。  

- Python (Flask)でWebサーバーとスケジューラを構築  
- Seleniumでnoteへのログイン・投稿を自動化  
- TweepyでTwitterへ投稿  
- APSchedulerで定期的にニュースを収集・投稿  

---

## 環境構築

### 1. 必要なもの
- Python 3.9以上
- Chromeブラウザ（Selenium用）
- ChromeDriver（ブラウザバージョンに合わせてインストール）

### 2. 依存パッケージのインストール

```bash
pip install -r requirements.txt
