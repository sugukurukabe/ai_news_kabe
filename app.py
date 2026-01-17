import streamlit as st
import google.generativeai as genai
import arxiv
import feedparser
import urllib.parse
import time
from datetime import datetime

# ==========================================
# 1. 設定 & デザイン
# ==========================================
st.set_page_config(page_title="AI Monitor & Library", page_icon="🧠", layout="wide")

st.markdown("""
<style>
    .stApp { font-family: "Helvetica Neue", Arial, sans-serif; }
    h1, h2, h3 { font-family: "Georgia", serif !important; color: #2c3e50; }
    .source-tag { font-size: 0.8rem; color: #7f8c8d; text-transform: uppercase; letter-spacing: 1px; }
    .saved-tag { background-color: #d4edda; color: #155724; padding: 2px 6px; border-radius: 4px; font-size: 0.8rem; }
</style>
""", unsafe_allow_html=True)

# セッション状態（保存箱）の初期化
if 'bookmarks' not in st.session_state:
    st.session_state.bookmarks = []

# APIキー設定 (Secrets or Input)
try:
    API_KEY = st.secrets["GOOGLE_API_KEY"]
except:
    API_KEY = "ここにAPIキー" # ローカル用

genai.configure(api_key=API_KEY)
model = genai.GenerativeModel('models/gemini-flash-latest')

# ==========================================
# 2. 定数・データソース
# ==========================================
ARXIV_CATEGORIES = {
    "LLM / NLP": "cs.CL", "Vision": "cs.CV", 
    "Robotics": "cs.RO", "Hardware": "cs.AR"
}
TECH_BLOGS = {
    "OpenAI": "https://openai.com/index.rss",
    "Anthropic": "https://www.anthropic.com/rss",
    "Google": "https://blog.google/technology/ai/rss/",
    "NVIDIA": "https://blogs.nvidia.com/feed/"
}
NEWS_TOPICS = ["DeepMind", "Tesla AI", "SpaceX", "NVIDIA AI"]

# ==========================================
# 3. 関数群
# ==========================================
def analyze_content(text, source_type):
    """AI要約"""
    prompt = f"""
    あなたはAI専門のキュレーターです。以下の{source_type}を読み、
    30秒で読める日本語要約を作成してください。
    
    フォーマット:
    **インパクト(1-10):** [数値] | **タグ:** [関連技術]
    **要点:**
    - [点1]
    - [点2]
    **一言:** [核心]

    テキスト: {text[:8000]}
    """
    try:
        response = model.generate_content(prompt)
        return response.text
    except: return "Error during analysis."

def fetch_data(cats, blogs, news, kw):
    """データ収集"""
    items = []
    # (コード短縮のためロジックは前回と同じですが、IDを追加します)
    client = arxiv.Client()
    for c in cats:
        s = arxiv.Search(query=f"cat:{ARXIV_CATEGORIES[c]}", max_results=2, sort_by=arxiv.SortCriterion.SubmittedDate)
        for r in client.results(s):
            items.append({"id": r.entry_id, "title": r.title, "source": "arXiv", "url": r.entry_id, "content": r.summary, "date": str(r.published.date()), "icon": "🎓"})
    
    for b in blogs:
        try:
            f = feedparser.parse(TECH_BLOGS[b])
            for e in f.entries[:2]:
                items.append({"id": e.link, "title": e.title, "source": b, "url": e.link, "content": e.get("summary",""), "date": "Blog", "icon": "🏢"})
        except: pass
            
    for n in news:
        try:
            url = f"https://news.google.com/rss/search?q={urllib.parse.quote(n+' when:7d')}&hl=en-US&gl=US&ceid=US:en"
            f = feedparser.parse(url)
            for e in f.entries[:2]:
                items.append({"id": e.link, "title": e.title, "source": "News", "url": e.link, "content": e.get("summary",""), "date": "Latest", "icon": "🌍"})
        except: pass
    return items

def toggle_bookmark(item, analysis_text):
    """保存/解除の切り替え"""
    # 既に保存済みかチェック
    existing = next((x for x in st.session_state.bookmarks if x['id'] == item['id']), None)
    if existing:
        st.session_state.bookmarks.remove(existing)
        st.toast(f"🗑️ Removed: {item['title'][:20]}...", icon="🗑️")
    else:
        # 保存するときに、AIの分析結果も一緒に保存する
        item['saved_analysis'] = analysis_text
        item['saved_at'] = datetime.now().strftime("%Y-%m-%d %H:%M")
        st.session_state.bookmarks.append(item)
        st.toast(f"💾 Saved: {item['title'][:20]}...", icon="✅")

# ==========================================
# 4. UI構築
# ==========================================
# サイドバーでモード切替
with st.sidebar:
    st.title("🧠 AI Brain")
    page = st.radio("Menu", ["📡 Discovery (Search)", "📚 My Library (Saved)"])
    st.divider()

if page == "📡 Discovery (Search)":
    # --- 検索モード ---
    st.header("Discovery Feed")
    
    # 設定パネル
    with st.expander("Search Settings", expanded=False):
        s_cats = st.multiselect("Papers", list(ARXIV_CATEGORIES.keys()), ["LLM / NLP"])
        s_blogs = st.multiselect("Blogs", list(TECH_BLOGS.keys()), ["OpenAI"])
        s_news = st.multiselect("News", NEWS_TOPICS, ["NVIDIA AI"])
        if st.button("Refresh Feed", type="primary"):
            st.session_state.feed_data = fetch_data(s_cats, s_blogs, s_news, "")
    
    # フィード表示
    if 'feed_data' in st.session_state:
        for item in st.session_state.feed_data:
            with st.container(border=True):
                # ヘッダー
                c1, c2 = st.columns([0.8, 0.2])
                c1.markdown(f"**{item['icon']} {item['source']}** | {item['date']}")
                c1.markdown(f"### {item['title']}")
                
                # 要約生成
                if f"summary_{item['id']}" not in st.session_state:
                    if st.button("AI解説を読む", key=f"btn_read_{item['id']}"):
                        with st.spinner("Analyzing..."):
                            st.session_state[f"summary_{item['id']}"] = analyze_content(item['content'], item['source'])
                            st.rerun()
                
                if f"summary_{item['id']}" in st.session_state:
                    analysis = st.session_state[f"summary_{item['id']}"]
                    st.info(analysis)
                    
                    # ボタン列
                    b1, b2 = st.columns(2)
                    with b1:
                        st.link_button("📄 原文へ", item['url'], use_container_width=True)
                    with b2:
                        # 保存ボタンの状態判定
                        is_saved = any(x['id'] == item['id'] for x in st.session_state.bookmarks)
                        btn_label = "✅ 保存済み (Library)" if is_saved else "🔖 保存する (Bookmark)"
                        btn_type = "secondary" if is_saved else "primary"
                        
                        if st.button(btn_label, key=f"save_{item['id']}", type=btn_type, use_container_width=True):
                            toggle_bookmark(item, analysis)
                            st.rerun()

    else:
        st.info("上の設定を開いて 'Refresh Feed' を押してください")

elif page == "📚 My Library (Saved)":
    # --- ライブラリモード ---
    st.header(f"My Library ({len(st.session_state.bookmarks)})")
    
    if not st.session_state.bookmarks:
        st.warning("まだ保存された記事はありません。Discoveryタブで記事を探しましょう！")
    
    # フィルタリング機能
    filter_text = st.text_input("🔍 ライブラリ内検索 (タイトルなど)", "")
    
    for item in st.session_state.bookmarks:
        # 検索フィルター
        if filter_text.lower() in item['title'].lower() or filter_text.lower() in item['source'].lower():
            
            with st.container(border=True):
                st.markdown(f"<span class='saved-tag'>Saved: {item['saved_at']}</span>", unsafe_allow_html=True)
                st.markdown(f"### {item['title']}")
                st.caption(f"{item['icon']} {item['source']}")
                
                # 保存された要約を表示
                with st.expander("AI解説メモを確認", expanded=False):
                    st.markdown(item.get('saved_analysis', 'No analysis saved.'))
                
                c1, c2 = st.columns(2)
                c1.link_button("原文を開く", item['url'], use_container_width=True)
                if c2.button("削除する", key=f"del_{item['id']}", use_container_width=True):
                    toggle_bookmark(item, "")
                    st.rerun()