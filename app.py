import streamlit as st
import google.generativeai as genai
import arxiv
import feedparser
import urllib.parse
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from time import mktime

# ==========================================
# 1. 設定 & 認証
# ==========================================
st.set_page_config(page_title="AI Intelligence Hub", page_icon="🧠", layout="wide")

st.markdown("""
<style>
    .stApp { font-family: "Hiragino Kaku Gothic ProN", "Meiryo", sans-serif; }
    h1, h2, h3 { color: #2c3e50; }
    .saved-tag { background-color: #d4edda; color: #155724; padding: 2px 6px; border-radius: 4px; font-size: 0.8rem; }
    .date-badge { background-color: #f1f3f5; color: #495057; padding: 2px 6px; border-radius: 4px; font-size: 0.75rem; margin-left: 8px;}
    div[data-testid="stButton"] button { width: 100%; }
</style>
""", unsafe_allow_html=True)

try:
    # Secretsの読み込みチェック
    if "GOOGLE_API_KEY" not in st.secrets:
        st.error("Secretsエラー: GOOGLE_API_KEY が見つかりません。")
        st.stop()
    if "gcp_service_account" not in st.secrets:
        st.error("Secretsエラー: [gcp_service_account] セクションが見つかりません。")
        st.stop()

    API_KEY = st.secrets["GOOGLE_API_KEY"]
    
    # シート接続設定
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds_dict = dict(st.secrets["gcp_service_account"])
    
    # 鍵の改行コード補正
    if "private_key" in creds_dict:
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)

    # ▼ID指定でオープン
    SPREADSHEET_ID = "1w4Xa9XxdGH26OxUCbxX3rV8jhajEESccVlIfPy9Bbpk" 
    sheet = client.open_by_key(SPREADSHEET_ID).sheet1

except Exception as e:
    # エラーの詳細を画面に出す
    st.error(f"⚠️ 起動エラー発生: {e}")
    # 認証情報のどの部分でコケたかヒントを出す
    st.warning("ヒント: Streamlit CloudのSecrets設定で、TOML形式が正しいか確認してください。")
    st.stop()

genai.configure(api_key=API_KEY)
model = genai.GenerativeModel('models/gemini-flash-latest')

# ==========================================
# 2. 定数 & 関数
# ==========================================
ARXIV_CATEGORIES = {
    "LLM / 自然言語処理": "cs.CL", "画像生成 / ビジョン": "cs.CV",
    "ロボティクス / エージェント": "cs.RO", "ハードウェア / エッジAI": "cs.AR"
}
TECH_BLOGS = {
    "OpenAI": "https://openai.com/index.rss", "Anthropic": "https://www.anthropic.com/rss",
    "Google AI": "https://blog.google/technology/ai/rss/", "NVIDIA Blog": "https://blogs.nvidia.com/feed/"
}
NEWS_TOPICS = ["DeepMind", "Tesla AI", "SpaceX", "NVIDIA AI", "SoftBank AI"]

def is_within_date_range(published_struct_time, days):
    if not published_struct_time: return True
    pub_date = datetime.fromtimestamp(mktime(published_struct_time))
    return (datetime.now() - pub_date).days <= days

def load_db():
    try: return sheet.get_all_records()
    except: return []

def save_to_db(item, memo):
    try:
        row = [item['id'], item['title'], item['url'], item['source'], datetime.now().strftime("%Y-%m-%d %H:%M"), memo]
        sheet.append_row(row)
        st.toast("💾 保存しました！", icon="☁️")
    except Exception as e:
        st.error(f"保存エラー: {e}")

def delete_from_db(item_id):
    try:
        cell = sheet.find(str(item_id))
        sheet.delete_rows(cell.row)
        st.toast("🗑️ 削除しました", icon="🗑️")
    except Exception as e:
        st.error(f"削除エラー: {e}")

def stream_analysis(text, source_type, placeholder):
    prompt = f"""
    あなたはAI専門の編集者です。以下の{source_type}を要約してください。
    フォーマット:
    **重要度:** [高/中/低] | **分野:** [タグ]
    **要点:**
    - [要点1]
    - [要点2]
    **一言:** [核心]
    テキスト: {text[:8000]}
    """
    try:
        response = model.generate_content(prompt, stream=True)
        full_text = ""
        for chunk in response:
            full_text += chunk.text
            placeholder.markdown(full_text)
        return full_text
    except: return "エラーが発生しました。"

def fetch_data(cats, blogs, news, days_range):
    items = []
    client = arxiv.Client()
    for c in cats:
        s = arxiv.Search(query=f"cat:{ARXIV_CATEGORIES[c]}", max_results=5, sort_by=arxiv.SortCriterion.SubmittedDate)
        for r in client.results(s):
            pub_date = r.published.replace(tzinfo=None)
            if (datetime.now() - pub_date).days <= days_range:
                items.append({"id": r.entry_id, "title": r.title, "source": "arXiv", "url": r.entry_id, "content": r.summary, "date": r.published.strftime("%Y-%m-%d"), "icon": "🎓"})
    
    for b in blogs:
        try:
            f = feedparser.parse(TECH_BLOGS[b])
            for e in f.entries:
                if hasattr(e, 'published_parsed') and not is_within_date_range(e.published_parsed, days_range): continue
                items.append({"id": e.link, "title": e.title, "source": b, "url": e.link, "content": e.get("summary", "")[:1000], "date": "Blog", "icon": "🏢"})
                if len([x for x in items if x['source'] == b]) >= 3: break
        except: pass

    for n in news:
        try:
            term = f"{days_range}d"
            url = f"https://news.google.com/rss/search?q={urllib.parse.quote(n+' when:'+term)}&hl=en-US&gl=US&ceid=US:en"
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
    st.header("📅 期間指定")
    date_options = {"24時間以内": 1, "3日以内": 3, "1週間以内": 7, "1ヶ月以内": 30}
    selected_period = st.selectbox("検索範囲", list(date_options.keys()), index=2)
    days_range = date_options[selected_period]
    st.divider()
    page = st.radio("メニュー", ["📡 探索", "☁️ ライブラリ"])

if 'generated_summaries' not in st.session_state:
    st.session_state.generated_summaries = {}

if page == "📡 探索":
    st.header(f"探索フィード ({selected_period})")
    
    try:
        db_data = load_db()
        saved_ids = [str(d['id']) for d in db_data]
    except:
        saved_ids = []

    with st.expander("詳細検索設定", expanded=False):
        s_cats = st.multiselect("論文", list(ARXIV_CATEGORIES.keys()), ["LLM / 自然言語処理"])
        s_blogs = st.multiselect("ブログ", list(TECH_BLOGS.keys()), ["OpenAI", "Anthropic"])
        s_news = st.multiselect("ニュース", NEWS_TOPICS, ["NVIDIA AI"])
        if st.button("情報を更新する", type="primary"):
            with st.spinner('記事を集めています...'):
                st.session_state.feed_data = fetch_data(s_cats, s_blogs, s_news, days_range)
    
    if 'feed_data' in st.session_state:
        if not st.session_state.feed_data:
            st.warning("記事が見つかりませんでした。")
        for item in st.session_state.feed_data:
            with st.container(border=True):
                st.markdown(f"**{item['icon']} {item['source']}** <span class='date-badge'>{selected_period}</span>", unsafe_allow_html=True)
                st.markdown(f"### {item['title']}")
                
                if item['id'] in st.session_state.generated_summaries:
                    st.info(st.session_state.generated_summaries[item['id']])
                else:
                    placeholder = st.empty()
                    if st.button("🤖 解説を読む", key=f"btn_{item['id']}"):
                        full_text = stream_analysis(item['content'], item['source'], placeholder)
                        st.session_state.generated_summaries[item['id']] = full_text
                
                if item['id'] in st.session_state.generated_summaries:
                    analysis = st.session_state.generated_summaries[item['id']]
                    c1, c2 = st.columns(2)
                    c1.link_button("📄 原文へ", item['url'], use_container_width=True)
                    if str(item['id']) in saved_ids:
                        c2.button("✅ 保存済み", disabled=True, use_container_width=True)
                    else:
                        if c2.button("💾 クラウド保存", key=f"save_{item['id']}", type="primary", use_container_width=True):
                            save_to_db(item, analysis)
                            st.rerun()

elif page == "☁️ ライブラリ":
    st.header("マイライブラリ")
    bookmarks = load_db()
    if not bookmarks:
        st.warning("保存された記事はありません。")
    else:
        for item in bookmarks:
            with st.container(border=True):
                st.markdown(f"<span class='saved-tag'>{item['saved_at']}</span>", unsafe_allow_html=True)
                st.markdown(f"### {item['title']}")
                with st.expander("AIメモ"):
                    st.markdown(item['ai_memo'])
                c1, c2 = st.columns(2)
                c1.link_button("原文", item['url'], use_container_width=True)
                if c2.button("削除", key=f"del_{item['id']}", use_container_width=True):
                    delete_from_db(item['id'])
                    st.rerun()
