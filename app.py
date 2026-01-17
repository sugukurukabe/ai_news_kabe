import streamlit as st
import google.generativeai as genai
import arxiv
import feedparser
import urllib.parse
import gspread
import json  # 追加
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from time import mktime

# ==========================================
# 1. 設定 & 認証
# ==========================================
st.set_page_config(page_title="AI Intelligence Hub", page_icon="🧠", layout="wide")
st.markdown("""<style>.stApp{font-family:"Hiragino Kaku Gothic ProN",sans-serif;}h1,h2,h3{color:#2c3e50;}div[data-testid="stButton"] button{width:100%;}</style>""", unsafe_allow_html=True)

try:
    # Secretsチェック
    if "GOOGLE_API_KEY" not in st.secrets:
        st.error("エラー: GOOGLE_API_KEY がSecretsにありません。")
        st.stop()

    API_KEY = st.secrets["GOOGLE_API_KEY"]
    
    # ▼▼▼【変更点】JSONとして丸ごと読み込む（これが一番確実です）▼▼▼
    if "GCP_JSON" in st.secrets:
        # 新しい方式（JSON貼り付け）
        creds_dict = json.loads(st.secrets["GCP_JSON"])
    elif "gcp_service_account" in st.secrets:
        # 古い方式（もし残っていれば）
        creds_dict = dict(st.secrets["gcp_service_account"])
        if "private_key" in creds_dict:
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
    else:
        st.error("エラー: Secretsに [GCP_JSON] が設定されていません。")
        st.stop()
        
    # シート接続
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)

    # ▼ID指定
    SPREADSHEET_ID = "1w4Xa9XxdGH26OxUCbxX3rV8jhajEESccVlIfPy9Bbpk" 
    sheet = client.open_by_key(SPREADSHEET_ID).sheet1

except Exception as e:
    st.error(f"⚠️ 起動エラー: {e}")
    st.stop()

genai.configure(api_key=API_KEY)
model = genai.GenerativeModel('models/gemini-flash-latest')

# ==========================================
# 2. 定数 & 関数
# ==========================================
ARXIV_CATEGORIES = {"LLM / 自然言語処理": "cs.CL", "画像生成 / ビジョン": "cs.CV", "ロボティクス": "cs.RO", "ハードウェア": "cs.AR"}
TECH_BLOGS = {"OpenAI": "https://openai.com/index.rss", "Anthropic": "https://www.anthropic.com/rss", "Google": "https://blog.google/technology/ai/rss/", "NVIDIA": "https://blogs.nvidia.com/feed/"}
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
        st.toast("💾 保存成功！", icon="☁️")
    except Exception as e:
        st.error(f"保存エラー: {e}")

def delete_from_db(item_id):
    try:
        cell = sheet.find(str(item_id))
        sheet.delete_rows(cell.row)
        st.rerun()
    except: pass

def stream_analysis(text, source_type, placeholder):
    try:
        response = model.generate_content(f"あなたはAI専門編集者です。次の{source_type}を要約してください。\nテキスト: {text[:8000]}", stream=True)
        full_text = ""
        for chunk in response:
            full_text += chunk.text
            placeholder.markdown(full_text)
        return full_text
    except: return "エラー"

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
    page = st.radio("Menu", ["探索", "ライブラリ"])

if 'gen_sums' not in st.session_state: st.session_state.gen_sums = {}

if page == "探索":
    st.header(f"探索フィード ({days_range}日以内)")
    try: saved_ids = [str(d['id']) for d in load_db()]
    except: saved_ids = []
    
    if st.button("更新", type="primary"):
        with st.spinner("収集中..."):
            st.session_state.feed = fetch_data(ARXIV_CATEGORIES.keys(), TECH_BLOGS.keys(), NEWS_TOPICS, days_range)

    if 'feed' in st.session_state:
        for item in st.session_state.feed:
            with st.container(border=True):
                st.markdown(f"**{item['icon']} {item['source']}**")
                st.markdown(f"### {item['title']}")
                if item['id'] in st.session_state.gen_sums:
                    st.info(st.session_state.gen_sums[item['id']])
                else:
                    if st.button("要約", key=f"btn_{item['id']}"):
                        st.session_state.gen_sums[item['id']] = stream_analysis(item['content'], item['source'], st.empty())
                
                if item['id'] in st.session_state.gen_sums:
                    if str(item['id']) not in saved_ids:
                        if st.button("保存", key=f"save_{item['id']}", type="primary"):
                            save_to_db(item, st.session_state.gen_sums[item['id']])
                            st.rerun()
                    else: st.button("保存済み", disabled=True, key=f"d_{item['id']}")
                    st.link_button("原文", item['url'])

elif page == "ライブラリ":
    st.header("保存済み")
    for item in load_db():
        with st.container(border=True):
            st.markdown(f"### {item['title']}")
            st.caption(item['saved_at'])
            with st.expander("メモ"): st.markdown(item['ai_memo'])
            c1,c2 = st.columns(2)
            c1.link_button("原文", item['url'])
            if c2.button("削除", key=f"del_{item['id']}"): delete_from_db(item['id'])
