import streamlit as st
import google.generativeai as genai
import arxiv
import feedparser
import urllib.parse
from datetime import datetime
from time import mktime

# ==========================================
# 1. 設定
# ==========================================
st.set_page_config(page_title="AI Intelligence Hub", page_icon="🧠", layout="wide")
st.markdown("""<style>.stApp{font-family:"Hiragino Kaku Gothic ProN",sans-serif;}h1,h2,h3{color:#2c3e50;}div[data-testid="stButton"] button{width:100%;}</style>""", unsafe_allow_html=True)

# エラーの原因になるデータベース接続を全削除しました
# APIキーだけあれば動きます
try:
    API_KEY = st.secrets["GOOGLE_API_KEY"]
except:
    # 万が一Secretsが読み込めない場合のエラー回避
    st.error("設定エラー: GOOGLE_API_KEY が設定されていません。")
    st.stop()

genai.configure(api_key=API_KEY)
model = genai.GenerativeModel('models/gemini-flash-latest')

# ==========================================
# 2. 定数 & 関数
# ==========================================
ARXIV_CATEGORIES = {"LLM": "cs.CL", "Vision": "cs.CV", "Robotics": "cs.RO", "Hardware": "cs.AR"}
TECH_BLOGS = {"OpenAI": "https://openai.com/index.rss", "Anthropic": "https://www.anthropic.com/rss", "Google": "https://blog.google/technology/ai/rss/", "NVIDIA": "https://blogs.nvidia.com/feed/"}
NEWS_TOPICS = ["DeepMind", "Tesla AI", "SpaceX", "NVIDIA AI", "SoftBank AI"]

def is_within_date_range(published_struct_time, days):
    if not published_struct_time: return True
    pub_date = datetime.fromtimestamp(mktime(published_struct_time))
    return (datetime.now() - pub_date).days <= days

def stream_analysis(text, source_type, placeholder):
    try:
        response = model.generate_content(f"あなたはAI専門編集者です。次の{source_type}を要約してください。\nテキスト: {text[:8000]}", stream=True)
        full_text = ""
        for chunk in response:
            full_text += chunk.text
            placeholder.markdown(full_text)
        return full_text
    except: return "エラーが発生しました。"

def fetch_data(cats, blogs, news, days_range):
    items = []
    # arXiv
    client = arxiv.Client()
    for c in cats:
        try:
            s = arxiv.Search(query=f"cat:{ARXIV_CATEGORIES[c]}", max_results=5, sort_by=arxiv.SortCriterion.SubmittedDate)
            for r in client.results(s):
                pub_date = r.published.replace(tzinfo=None)
                if (datetime.now() - pub_date).days <= days_range:
                    items.append({"id": r.entry_id, "title": r.title, "source": "arXiv", "url": r.entry_id, "content": r.summary, "date": r.published.strftime("%Y-%m-%d"), "icon": "🎓"})
        except: pass
    
    # Blogs
    for b in blogs:
        try:
            f = feedparser.parse(TECH_BLOGS[b])
            for e in f.entries:
                if hasattr(e, 'published_parsed') and not is_within_date_range(e.published_parsed, days_range): continue
                items.append({"id": e.link, "title": e.title, "source": b, "url": e.link, "content": e.get("summary", "")[:1000], "date": "Blog", "icon": "🏢"})
                if len([x for x in items if x['source'] == b]) >= 3: break
        except: pass
        
    # News
    for n in news:
        try:
            url = f"https://news.google.com/rss/search?q={urllib.parse.quote(n+' when:'+str(days_range)+'d')}&hl=en-US&gl=US&ceid=US:en"
            f = feedparser.parse(url)
            for e in f.entries[:3]:
                items.append({"id": e.link, "title": e.title, "source": "News", "url": e.link, "content": e.get("summary", ""), "date": "News", "icon": "🌍"})
        except: pass
    return items

# ==========================================
# 3. UI構築
# ==========================================
with st.sidebar:
    st.title("🧠 AI Intelligence Hub")
    days_range = st.selectbox("期間", [1, 3, 7, 30], index=2, format_func=lambda x: f"{x}日以内")
    st.caption("※現在、保存機能は停止中です")

if 'gen_sums' not in st.session_state: st.session_state.gen_sums = {}

st.header(f"探索フィード ({days_range}日以内)")

if st.button("情報を更新する", type="primary"):
    with st.spinner("世界中のAI情報を収集中..."):
        st.session_state.feed = fetch_data(ARXIV_CATEGORIES.keys(), TECH_BLOGS.keys(), NEWS_TOPICS, days_range)

if 'feed' in st.session_state:
    if not st.session_state.feed:
        st.info("新しい記事は見つかりませんでした。期間を広げてみてください。")
    
    for item in st.session_state.feed:
        with st.container(border=True):
            st.markdown(f"**{item['icon']} {item['source']}**")
            st.markdown(f"### {item['title']}")
            
            if item['id'] in st.session_state.gen_sums:
                st.info(st.session_state.gen_sums[item['id']])
            else:
                placeholder = st.empty()
                if st.button("🤖 AI要約を読む", key=f"btn_{item['id']}"):
                    st.session_state.gen_sums[item['id']] = stream_analysis(item['content'], item['source'], placeholder)
            
            st.link_button("📄 原文を読む", item['url'])

elif 'history' not in st.session_state:
    st.info("「情報を更新する」ボタンを押して、最新のAIトレンドをチェックしましょう！")
