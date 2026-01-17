import streamlit as st
import google.generativeai as genai
import arxiv
import feedparser
import urllib.parse
from datetime import datetime
from time import mktime

# ==========================================
# 1. 設定 & ソース定義
# ==========================================
st.set_page_config(page_title="Global AI News", page_icon="🌎", layout="wide")
st.markdown("""<style>.stApp{font-family:"Hiragino Kaku Gothic ProN",sans-serif;}h1,h2,h3{color:#2c3e50;}div[data-testid="stButton"] button{width:100%;}</style>""", unsafe_allow_html=True)

try:
    API_KEY = st.secrets["GOOGLE_API_KEY"]
except:
    st.error("設定エラー: GOOGLE_API_KEY が設定されていません。")
    st.stop()

genai.configure(api_key=API_KEY)
model = genai.GenerativeModel('models/gemini-flash-latest')

# --- ▼▼▼ ここで新しいソースを追加しました ▼▼▼ ---
ARXIV_CATEGORIES = {
    "LLM / 言語モデル": "cs.CL", 
    "Vision / 画像生成": "cs.CV", 
    "Robotics / ロボット": "cs.RO", 
    "AI General / 全般": "cs.AI"
}

# 主要AI企業の公式ブログRSS
TECH_BLOGS = {
    "OpenAI": "https://openai.com/index.rss",
    "Anthropic (Claude)": "https://www.anthropic.com/rss",
    "Google DeepMind": "https://deepmind.google/blog/rss.xml", # DeepMind専用
    "Google AI": "https://blog.google/technology/ai/rss/",
    "NVIDIA": "https://blogs.nvidia.com/feed/",
    "Microsoft Azure AI": "https://azure.microsoft.com/en-us/blog/feed/topics/artificial-intelligence/",
    "AWS Machine Learning": "https://aws.amazon.com/blogs/machine-learning/feed/"
}

# DeepSeekなどはRSSがない場合が多いので、ニュース検索キーワードに追加
NEWS_TOPICS = [
    "DeepSeek",       # 中国の注目AI
    "Qwen Alibaba",   # アリババのAI
    "OpenAI o1",      # 最新モデル
    "Gemini 1.5",     # Google
    "Claude 3.5",     # Anthropic
    "Meta Llama 3",   # Meta
    "Sakana AI"       # 日本発AI
]

# ==========================================
# 2. 関数群
# ==========================================
def is_within_date_range(published_struct_time, days):
    if not published_struct_time: return True
    pub_date = datetime.fromtimestamp(mktime(published_struct_time))
    return (datetime.now() - pub_date).days <= days

def stream_analysis(text, source_type, placeholder):
    try:
        # 日本語で要約するようにプロンプトを調整
        prompt = f"""
        あなたはプロのAIニュース編集者です。以下の{source_type}の内容を日本語で要約してください。
        専門用語はなるべく残しつつ、初心者にもわかりやすく解説してください。
        
        ## フォーマット
        **3行まとめ:**
        - [要点1]
        - [要点2]
        - [要点3]
        
        **詳細:** [内容の要約]
        
        対象テキスト: {text[:10000]}
        """
        response = model.generate_content(prompt, stream=True)
        full_text = ""
        for chunk in response:
            full_text += chunk.text
            placeholder.markdown(full_text)
        return full_text
    except: return "エラーが発生しました。"

def fetch_data(cats, blogs, news, days_range):
    items = []
    
    # 1. arXiv (論文)
    client = arxiv.Client()
    for c in cats:
        try:
            s = arxiv.Search(query=f"cat:{ARXIV_CATEGORIES[c]}", max_results=3, sort_by=arxiv.SortCriterion.SubmittedDate)
            for r in client.results(s):
                pub_date = r.published.replace(tzinfo=None)
                if (datetime.now() - pub_date).days <= days_range:
                    items.append({
                        "id": r.entry_id, # 重複チェック用のID
                        "title": r.title,
                        "source": "arXiv",
                        "url": r.entry_id,
                        "content": r.summary,
                        "date": r.published.strftime("%Y-%m-%d"),
                        "icon": "🎓"
                    })
        except: pass
    
    # 2. Tech Blogs (企業ブログ)
    for name, url in blogs.items():
        try:
            f = feedparser.parse(url)
            for e in f.entries:
                if hasattr(e, 'published_parsed') and not is_within_date_range(e.published_parsed, days_range): continue
                items.append({
                    "id": e.link,
                    "title": e.title,
                    "source": name,
                    "url": e.link,
                    "content": e.get("summary", "")[:1500] + "...",
                    "date": "Blog",
                    "icon": "🏢"
                })
                if len([x for x in items if x['source'] == name]) >= 3: break
        except: pass
        
    # 3. Google News Search (DeepSeekなどのニュース)
    for n in news:
        try:
            # 英語ニュースの方が情報が早いため en-US で検索
            term = f"{days_range}d"
            rss_url = f"https://news.google.com/rss/search?q={urllib.parse.quote(n+' when:'+term)}&hl=en-US&gl=US&ceid=US:en"
            f = feedparser.parse(rss_url)
            for e in f.entries[:2]: # 各トピック2件まで
                items.append({
                    "id": e.link,
                    "title": e.title,
                    "source": f"News ({n})",
                    "url": e.link,
                    "content": e.get("summary", ""),
                    "date": "News",
                    "icon": "🌍"
                })
        except: pass
    
    return items

# ==========================================
# 3. UI構築
# ==========================================
with st.sidebar:
    st.title("🌎 Global AI News")
    days_range = st.selectbox("期間", [1, 3, 7, 30], index=1, format_func=lambda x: f"{x}日以内")
    st.info("DeepSeek, DeepMind, OpenAI, Anthropic等の最新情報を収集します。")

if 'gen_sums' not in st.session_state: st.session_state.gen_sums = {}

st.header(f"探索フィード ({days_range}日以内)")

if st.button("情報を更新する", type="primary"):
    with st.spinner("世界中のAI論文・ブログ・ニュースを収集中..."):
        raw_data = fetch_data(ARXIV_CATEGORIES.keys(), TECH_BLOGS, NEWS_TOPICS, days_range)
        
        # ▼▼▼【重要修正】重複削除ロジック ▼▼▼
        # IDが同じ記事は1つにまとめる
        seen_ids = set()
        unique_data = []
        for item in raw_data:
            if item['id'] not in seen_ids:
                unique_data.append(item)
                seen_ids.add(item['id'])
        
        st.session_state.feed = unique_data

if 'feed' in st.session_state:
    if not st.session_state.feed:
        st.warning("記事が見つかりませんでした。期間を広げるか、更新ボタンを押してください。")
    
    # enumerate(i) を使って、通し番号を取得
    for i, item in enumerate(st.session_state.feed):
        with st.container(border=True):
            st.markdown(f"**{item['icon']} {item['source']}**")
            st.markdown(f"### {item['title']}")
            
            # 要約エリア
            if item['id'] in st.session_state.gen_sums:
                st.success(st.session_state.gen_sums[item['id']])
            else:
                placeholder = st.empty()
                # ▼▼▼【エラー修正】keyに番号(i)を含めて絶対に重複させない ▼▼▼
                if st.button("🤖 AI要約を読む", key=f"btn_{i}_{item['id']}"):
                    st.session_state.gen_sums[item['id']] = stream_analysis(item['content'], item['source'], placeholder)
            
            st.link_button("📄 原文を読む", item['url'])

elif 'history' not in st.session_state:
    st.info("サイドバーで期間を選んで「情報を更新する」を押してください。")
