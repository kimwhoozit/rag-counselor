import os
import json
import streamlit as st
import pandas as pd
import tempfile
import shutil
from datetime import datetime
import database
import llm_service
import utils
import gdrive_service

# 1. Page Configuration & Theme
st.set_page_config(
    page_title="프로젝트 성장형 AI 상담사",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Initialize Database & Attempt Recovery if missing
DB_PATH = "knowledge_base.db"
GD_CREDS_FILE = "gdrive_credentials.json"

if not os.path.exists(DB_PATH):
    # Try to download from Google Drive
    gdrive_folder_id = st.secrets.get("gdrive_folder_id", os.environ.get("gdrive_folder_id", ""))
    has_credentials = os.path.exists(GD_CREDS_FILE) or "GDRIVE_CREDS_JSON" in os.environ or "GDRIVE_CREDS_JSON" in st.secrets
    if has_credentials and gdrive_folder_id:
        try:
            if "GDRIVE_CREDS_JSON" in st.secrets:
                cred_info = st.secrets["GDRIVE_CREDS_JSON"]
                if isinstance(cred_info, str):
                    cred_info = json.loads(cred_info)
            elif "GDRIVE_CREDS_JSON" in os.environ:
                cred_info = json.loads(os.environ["GDRIVE_CREDS_JSON"])
            else:
                with open(GD_CREDS_FILE, "r") as f:
                    cred_info = json.load(f)
            service = gdrive_service.get_gdrive_service(cred_info)
            gdrive_service.download_db_file(service, gdrive_folder_id, DB_PATH)
        except Exception:
            pass # Fallback to default init_db

database.init_db()

# Create default admin if users list is empty
if not database.get_all_users():
    database.create_user("admin", "admin1234", "admin")

# Check Authentication State
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "username" not in st.session_state:
    st.session_state.username = None
if "role" not in st.session_state:
    st.session_state.role = None

# Custom Premium Styling
st.markdown("""
<style>
    /* Dark Theme Accent & Custom Elements */
    .stApp {
        background-color: #0e1117;
        color: #e2e8f0;
    }
    
    /* Main body markdown text, paragraphs, lists, list items - FORCE LEGIBLE CONTRAST */
    .stMarkdown p, .stMarkdown li, .stMarkdown ul, .stMarkdown ol, .stMarkdown span {
        color: #f1f5f9 !important;
        font-size: 1.05rem !important;
        line-height: 1.6 !important;
    }
    
    /* Chat message text contrast improvements */
    [data-testid="stChatMessage"] p, [data-testid="stChatMessage"] li, [data-testid="stChatMessage"] span {
        color: #f8fafc !important;
        font-size: 1.08rem !important;
        line-height: 1.65 !important;
    }
    
    h1, h2, h3, h4 {
        font-family: 'Outfit', 'Inter', sans-serif;
        color: #ffffff !important;
        font-weight: 700;
    }
    
    .main-title {
        background: linear-gradient(90deg, #3b82f6 0%, #10b981 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 2.8rem;
        margin-bottom: 0.5rem;
    }
    
    .sub-title {
        color: #a855f7 !important; /* Premium lilac accent */
        font-size: 1.1rem;
        margin-bottom: 2rem;
    }
    
    /* Expander card decoration */
    .stExpander {
        border: 1px solid #334155 !important;
        border-radius: 8px !important;
        background-color: #1e293b44 !important;
    }
    
    /* Buttons */
    .stButton>button {
        transition: all 0.3s ease;
    }
    
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
    }
    
    /* Premium dashboard widgets styling */
    .custom-card {
        background-color: #1e293b66;
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 1.5rem;
        margin-bottom: 1.2rem;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }
    
    .metric-card {
        text-align: center;
        padding: 1.2rem;
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        border: 1px solid #3b82f633;
        border-radius: 10px;
        margin-bottom: 1rem;
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.3);
    }
    
    .metric-val {
        font-size: 2.2rem;
        font-weight: 800;
        background: linear-gradient(90deg, #60a5fa 0%, #34d399 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        line-height: 1.2;
    }
    
    .metric-label {
        font-size: 0.85rem;
        color: #94a3b8;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-top: 0.4rem;
    }
    
    /* 텍스트 입력창 및 텍스트 영역의 글자색 선명하게 강제 지정 */
    input, textarea, [data-testid="stChatInput"] textarea {
        color: #ffffff !important;
        -webkit-text-fill-color: #ffffff !important;
        background-color: #1e293b !important;
    }
    
    /* 상단 메뉴바 화면 상단에 완전 고정 (Fixed Header) */
    div[data-key="sticky_nav_container"] {
        position: fixed !important;
        top: 0px !important; /* 최상단에 완전 고정 */
        left: 0px !important;
        right: 0px !important;
        z-index: 99999 !important;
        background-color: #0e1117 !important;
        padding-top: 15px !important;
        padding-bottom: 15px !important;
        padding-left: 5rem !important; /* 좌우 마진 조율 */
        padding-right: 5rem !important;
        border-bottom: 1.5px solid #1e293b !important;
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.3), 0 4px 6px -4px rgba(0, 0, 0, 0.3) !important;
    }
    
    /* 본문 영역 상단을 메뉴바 높이만큼 내려주어 겹침 방지 */
    div.block-container {
        padding-top: 5.5rem !important;
    }
</style>
""", unsafe_allow_html=True)

# Login Gate
if not st.session_state.authenticated:
    st.markdown('<div class="main-title" style="text-align:center; margin-top: 3rem;">🌱 프로젝트 상담사</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-title" style="text-align:center; margin-bottom: 3rem;">로그인 페이지</div>', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.container(border=True):
            st.markdown("### 🔒 보안 로그인")
            login_user = st.text_input("아이디(ID)", placeholder="아이디를 입력하세요", key="login_username_input")
            login_pass = st.text_input("비밀번호(PW)", type="password", placeholder="비밀번호를 입력하세요", key="login_password_input")
            
            if st.button("로그인 실행", type="primary", use_container_width=True):
                if database.verify_user(login_user, login_pass):
                    st.session_state.authenticated = True
                    st.session_state.username = login_user
                    
                    # Retrieve role
                    users = database.get_all_users()
                    user_role = "user"
                    for u in users:
                        if u["username"] == login_user:
                            user_role = u["role"]
                            break
                    st.session_state.role = user_role
                    st.success("로그인 성공!")
                    st.rerun()
                else:
                    st.error("❌ 아이디 또는 비밀번호가 올바르지 않습니다.")
            

    st.stop()

# Helper constants
DOCS_DIR = "documents"
GD_CREDS_FILE = "gdrive_credentials.json"

# Utility functions
def scan_documents_folder():
    """Scans the DOCS_DIR recursively and returns a dict mapping relative path -> last_modified_time."""
    if not os.path.exists(DOCS_DIR):
        os.makedirs(DOCS_DIR)
        
    supported_extensions = {'.txt', '.md', '.docx', '.xlsx', '.xls', '.pdf', '.hwpx', '.hwp'}
    files_state = {}
    
    for root, dirs, files in os.walk(DOCS_DIR):
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in supported_extensions:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, DOCS_DIR)
                rel_path = rel_path.replace("\\", "/")
                try:
                    mtime = os.path.getmtime(full_path)
                    files_state[rel_path] = mtime
                except Exception:
                    continue
    return files_state

def calculate_sync_diff(local_files, indexed_files):
    """Compares local folder state and DB state to find additions, modifications, and deletions."""
    added = []
    modified = []
    deleted = []
    
    for rel_path, mtime in local_files.items():
        if rel_path not in indexed_files:
            added.append(rel_path)
        elif mtime > indexed_files[rel_path] + 1.0: # 1 second buffer
            modified.append(rel_path)
            
    for rel_path in indexed_files.keys():
        if rel_path not in local_files:
            deleted.append(rel_path)
            
    return added, modified, deleted

def sync_documents(api_key, added, modified, deleted, local_files):
    """Executes indexing sync for the local documents."""
    if not api_key:
        st.error("API Key가 설정되어 있지 않습니다.")
        return
        
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    total_steps = len(added) + len(modified) + len(deleted)
    if total_steps == 0:
        status_text.write("✨ 동기화할 대상이 없습니다.")
        return
        
    current_step = 0
    
    # 1. Process deletions
    for rel_path in deleted:
        status_text.write(f"🗑️ `{rel_path}` 인덱싱 정보 제거 중...")
        database.delete_document_by_title_prefix(rel_path)
        database.remove_indexed_file_record(rel_path)
        
        # Also clean up the physical file if it was deleted via Google Drive
        local_path = os.path.join(DOCS_DIR, rel_path)
        if os.path.exists(local_path):
            try:
                os.remove(local_path)
            except Exception:
                pass
                
        current_step += 1
        progress_bar.progress(current_step / total_steps)
        
    # 2. Process modifications
    for rel_path in modified:
        status_text.write(f"🔄 `{rel_path}` 변경사항 재인덱싱 중...")
        database.delete_document_by_title_prefix(rel_path)
        database.remove_indexed_file_record(rel_path)
        
        full_path = os.path.join(DOCS_DIR, rel_path)
        try:
            content = utils.parse_file(full_path)
            chunks = utils.split_text(content)
            embeddings = llm_service.get_embeddings_batch(chunks, api_key)
            
            for c_idx, chunk in enumerate(chunks):
                database.add_document(
                    title=f"{rel_path} (조각 {c_idx+1})",
                    content=chunk,
                    category="document",
                    embedding=embeddings[c_idx]
                )
            
            mtime = local_files[rel_path]
            database.mark_file_indexed(rel_path, mtime)
        except Exception as e:
            st.error(f"오류 발생 ({rel_path}): {str(e)}")
            
        current_step += 1
        progress_bar.progress(current_step / total_steps)
        
    # 3. Process additions
    for rel_path in added:
        status_text.write(f"⚙️ `{rel_path}` 신규 임베딩 분석 중...")
        full_path = os.path.join(DOCS_DIR, rel_path)
        try:
            content = utils.parse_file(full_path)
            chunks = utils.split_text(content)
            embeddings = llm_service.get_embeddings_batch(chunks, api_key)
            
            for c_idx, chunk in enumerate(chunks):
                database.add_document(
                    title=f"{rel_path} (조각 {c_idx+1})",
                    content=chunk,
                    category="document",
                    embedding=embeddings[c_idx]
                )
            
            mtime = local_files[rel_path]
            database.mark_file_indexed(rel_path, mtime)
        except Exception as e:
            st.error(f"오류 발생 ({rel_path}): {str(e)}")
            
        current_step += 1
        progress_bar.progress(current_step / total_steps)
        
    status_text.write("✨ 동기화가 성공적으로 완료되었습니다!")
    st.toast("✅ 동기화 완료!", icon="🎉")

def parse_rfc3339(rfc_str: str) -> float:
    """Parses RFC3339 timestamps (from Google Drive) into local timestamp float."""
    import re
    clean_str = re.sub(r'\.\d+', '', rfc_str)  # strip milliseconds
    if clean_str.endswith('Z'):
        clean_str = clean_str[:-1] + '+00:00'
    clean_str = re.sub(r'([+-]\d{2}):(\d{2})$', r'\1\2', clean_str) # standard timezone format
    dt = datetime.strptime(clean_str, "%Y-%m-%dT%H:%M:%S%z")
    return dt.timestamp()

# Session State Setup
if "messages" not in st.session_state:
    st.session_state.messages = []
if "last_response" not in st.session_state:
    st.session_state.last_response = None
if "session_id" not in st.session_state:
    st.session_state.session_id = f"session_{st.session_state.username}"

# Reload past chat messages from DB into Session State if empty
if not st.session_state.messages:
    db_history = database.get_chat_history(st.session_state.session_id)
    st.session_state.messages = db_history

# 2. Sidebar Layout (Options & Settings Popup Panel)
with st.sidebar:
    st.markdown('<div style="font-size: 1.5rem; font-weight: 800; background: linear-gradient(90deg, #3b82f6 0%, #10b981 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin-bottom: 1rem;">⚙️ 설정 및 시스템 관리</div>', unsafe_allow_html=True)
    
    # Active User Info
    st.markdown(f"👤 **접속 계정**: `{st.session_state.username}`")
    st.markdown(f"🔑 **접속 권한**: `{'관리자' if st.session_state.role == 'admin' else '일반 사용자'}`")
    
    if st.button("🚪 로그아웃", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.username = None
        st.session_state.role = None
        st.session_state.messages = []
        st.session_state.last_response = None
        st.rerun()
        
    st.markdown("---")
    
    # API Configuration (Only visible to admin)
    if st.session_state.role == "admin":
        env_api_key = st.secrets.get("GEMINI_API_KEY", os.environ.get("GEMINI_API_KEY", ""))
        st.markdown("#### 🔑 API Key 설정")
        api_key_input = st.text_input(
            "Gemini API Key:",
            type="password",
            value=st.session_state.get("gemini_api_key", env_api_key),
            help="Google AI Studio에서 발급받은 Gemini API Key를 입력하세요.",
            key="gdrive_api_key_input"
        )
        if api_key_input:
            st.session_state.gemini_api_key = api_key_input
        st.markdown("---")
    
    # Model Configuration
    st.markdown("#### ⚙️ 추론 모델 설정")
    selected_model = st.selectbox(
        "추론 LLM 모델 선택:",
        options=["gemini-2.5-flash", "gemini-3.5-flash", "gemini-1.5-flash", "gemini-1.5-pro"],
        index=0,
        help="추론 성능과 속도에 맞는 모델을 선택합니다.",
        key="sb_model_selector"
    )
    st.markdown("---")

# 3. Main Dashboard Layout Header
st.markdown('<div class="main-title">🌱 프로젝트 상담사</div>', unsafe_allow_html=True)

# Horizontal Navigation Menu (Segmented Control wrapped in Sticky Container)
with st.container(key="sticky_nav_container"):
    menu = st.segmented_control(
        "📍 메뉴 이동",
        options=["💬 서류 검토 및 상담 (RAG)", "📚 구글 드라이브 지식 관리", "⚙️ 시스템 설정 및 가이드"],
        default="💬 서류 검토 및 상담 (RAG)",
        label_visibility="collapsed"
    )

# ==========================================
# Menu 1: 대화 및 서류 검토
# ==========================================
if menu == "💬 서류 검토 및 상담 (RAG)":
    # Warning check
    if not st.session_state.get("gemini_api_key"):
        st.warning("⚠️ 왼쪽 상단 햄버거 메뉴(⚙️)를 열어 Gemini API Key를 먼저 입력하셔야 질문에 답변할 수 있습니다.")
        
    # Displays past conversation messages
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["message"])
            
    # 입력창 바로 위에 실시간 웹검색 토글 및 대화 리셋 버튼 수평 가로 배치
    c_toggle, c_reset = st.columns([3, 1])
    with c_toggle:
        enable_search = st.toggle(
            "🌐 실시간 웹 검색 연동",
            value=st.session_state.get("enable_search", True),
            help="고시, 시설기준, 최신 법령 검색이 필요할 때 Google Search를 연동하여 근거를 마련합니다.",
            key="main_page_web_search_toggle"
        )
        st.session_state.enable_search = enable_search
    with c_reset:
        if st.button("🧹 대화 기록 리셋", use_container_width=True, key="btn_reset_chat_main"):
            database.clear_chat_history(st.session_state.session_id)
            st.session_state.messages = []
            st.session_state.last_response = None
            st.toast("대화 기록이 청소되었습니다.")
            st.rerun()
            
    # Input field
    if prompt := st.chat_input("프로젝트 서류 검토 및 기준 법령에 대해 물어보세요..."):
        # Display user message
        with st.chat_message("user"):
            st.write(prompt)
        # Store user message
        database.save_chat_message(st.session_state.session_id, "user", prompt)
        st.session_state.messages.append({"role": "user", "message": prompt})
        
        # Inference progress indicator
        with st.chat_message("assistant"):
            with st.spinner("로컬 지식베이스 검색 및 외부 법령/기준 검토 중..."):
                try:
                    # 1. API key checks
                    api_key = st.session_state.get("gemini_api_key")
                    if not api_key:
                        st.error("API Key가 누락되었습니다. 왼쪽 상단 ⚙️ 설정에서 API Key를 설정해 주세요.")
                        st.stop()
                        
                    # 2. Vector DB search (generate query embedding first)
                    query_embedding = llm_service.get_embedding(prompt, api_key)
                    # Search documents in both category
                    retrieved_docs = database.search_similar_documents(query_embedding, limit=5)
                    
                    # 3. Model Generation
                    result = llm_service.generate_answer(
                        query=prompt,
                        retrieved_docs=retrieved_docs,
                        chat_history=st.session_state.messages[:-1], # pass previous history
                        api_key=api_key,
                        enable_search=enable_search,
                        model_name=selected_model
                    )
                    
                    answer = result["answer"]
                    sources = result["sources"]
                    
                    # Display Answer
                    st.write(answer)
                    
                    # Display Local Source References if retrieved
                    if retrieved_docs:
                        with st.expander("🔍 로컬 지식베이스 매칭 내역", expanded=False):
                            for d in retrieved_docs:
                                category_label = "일반 문서" if d['category'] == 'document' else "이전 성장형 답변"
                                st.markdown(f"**[{category_label}] {d['title']}** (유사도: `{d['score']:.4f}`)")
                                st.write(d['content'][:300] + "..." if len(d['content']) > 300 else d['content'])
                                st.markdown("---")
                                
                    # Display Web Search Sources if exist
                    if sources:
                        with st.expander("🌐 실시간 웹 검색 출처", expanded=False):
                            for s in sources:
                                st.markdown(f"- [{s['title']}]({s['uri']})")
                                
                    # Save AI Message
                    database.save_chat_message(st.session_state.session_id, "assistant", answer)
                    st.session_state.messages.append({"role": "assistant", "message": answer})
                    
                    # Save for learning feedback loop
                    st.session_state.last_response = {
                        "query": prompt,
                        "answer": answer
                    }
                    st.session_state.scroll_to_top = True
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"오류가 발생했습니다: {str(e)}")

    # 4. Learning feedback loop UI block
    if st.session_state.last_response:
        st.markdown("---")
        with st.container(border=True):
            st.markdown("### 🌱 성장형 학습 피드백 루프")
            st.write("위 AI 상담사의 답변을 **다음 상담/검토 시 자동으로 반영**할 수 있도록 데이터베이스에 등록하시겠습니까?")
            
            learn_title = st.text_input(
                "질문 키워드/상황 요약:", 
                value=st.session_state.last_response["query"],
                help="이 키워드/상황과 유사한 다음 질문이 인입될 때 이 답변이 학습 지식으로 인출되어 답변에 활용됩니다.",
                key="feedback_learn_title_input"
            )
            
            c1, c2 = st.columns([1, 4])
            with c1:
                if st.button("🌱 학습 등록 완료", type="primary", use_container_width=True, key="btn_learn_submit"):
                    api_key = st.session_state.get("gemini_api_key")
                    if api_key:
                        with st.spinner("학습 답변 분석 및 지식 인덱싱 생성 중..."):
                            try:
                                combined_text = f"상황/질문: {learn_title}\n검토된 모범 답변: {st.session_state.last_response['answer']}"
                                emb = llm_service.get_embedding(combined_text, api_key)
                                
                                database.add_document(
                                    title=learn_title,
                                    content=st.session_state.last_response['answer'],
                                    category="qa_history",
                                    embedding=emb
                                )
                                st.success("지식베이스에 학습 완료되었습니다! 다음 질문 검토 시 적극 참조됩니다.")
                                
                                # Backup DB to Google Drive
                                try:
                                    gdrive_folder_id = st.secrets.get("gdrive_folder_id", os.environ.get("gdrive_folder_id", ""))
                                    has_credentials = os.path.exists(GD_CREDS_FILE) or "GDRIVE_CREDS_JSON" in os.environ or "GDRIVE_CREDS_JSON" in st.secrets
                                    if has_credentials and gdrive_folder_id:
                                        if "GDRIVE_CREDS_JSON" in st.secrets:
                                            cred_info = st.secrets["GDRIVE_CREDS_JSON"]
                                            if isinstance(cred_info, str):
                                                cred_info = json.loads(cred_info)
                                        elif "GDRIVE_CREDS_JSON" in os.environ:
                                            cred_info = json.loads(os.environ["GDRIVE_CREDS_JSON"])
                                        else:
                                            with open(GD_CREDS_FILE, "r") as f:
                                                cred_info = json.load(f)
                                        service = gdrive_service.get_gdrive_service(cred_info)
                                        gdrive_service.upload_db_file(service, gdrive_folder_id, DB_PATH)
                                except Exception as backup_err:
                                    st.warning(f"⚠️ 학습 등록은 완료되었으나 DB 백업에 실패했습니다: {str(backup_err)}")
                                
                                st.session_state.last_response = None
                                st.rerun()
                            except Exception as e:
                                st.error(f"학습 실패: {str(e)}")
                    else:
                        st.error("API Key가 필요합니다.")
            with c2:
                if st.button("🗑️ 건너뛰기", use_container_width=True, key="btn_skip_feedback"):
                    st.session_state.last_response = None
                    st.rerun()

    # 5. Scroll to top trigger script (Ensures reading from the beginning of response)
    if st.session_state.get("scroll_to_top", False):
        st.session_state.scroll_to_top = False
        scroll_js = """
        <script>
            var body = window.parent.document.querySelector(".main");
            if (body) {
                body.scrollTop = 0;
            }
        </script>
        """
        st.markdown(scroll_js, unsafe_allow_html=True)

# ==========================================
# Menu 2: 지식 관리 및 동기화
# ==========================================
elif menu == "📚 구글 드라이브 지식 관리":
    st.markdown("### 📚 지식베이스 관리 및 다중 소스 동기화")
    
    # 1. Statistics Cards at the top
    all_docs = database.get_all_documents()
    total_docs = len(all_docs)
    doc_count = sum(1 for d in all_docs if d['category'] == 'document')
    qa_count = sum(1 for d in all_docs if d['category'] == 'qa_history')
    
    c_m1, c_m2, c_m3 = st.columns(3)
    with c_m1:
        st.markdown(f'<div class="metric-card"><div class="metric-val">{total_docs}</div><div class="metric-label">총 누적 지식 조각</div></div>', unsafe_allow_html=True)
    with c_m2:
        st.markdown(f'<div class="metric-card"><div class="metric-val">{doc_count}</div><div class="metric-label">문서 추출 지식</div></div>', unsafe_allow_html=True)
    with c_m3:
        st.markdown(f'<div class="metric-card"><div class="metric-val">{qa_count}</div><div class="metric-label">성장형 학습 피드백</div></div>', unsafe_allow_html=True)
    
    st.markdown("---")
    
    col_left, col_right = st.columns([1, 1])
    
    with col_left:
        api_key = st.session_state.get("gemini_api_key")
        
        # Section A: 구글 드라이브 연동 설정 카드
        with st.container(border=True):
            st.markdown("#### ☁️ 구글 드라이브 연동 설정")
            st.write("구글 클라우드 서비스 계정 키(JSON)와 동기화할 폴더 ID를 설정합니다.")
            
            # Google Drive configuration inputs
            env_folder_id = st.secrets.get("gdrive_folder_id", os.environ.get("gdrive_folder_id", ""))
            raw_folder_id = st.text_input(
                "구글 드라이브 폴더 ID (Folder ID) 또는 URL:",
                value=st.session_state.get("gdrive_folder_id", env_folder_id),
                help="구글 드라이브 폴더 전체 URL 또는 맨 뒷부분의 폴더 ID 문자열을 입력하세요.",
                key="gdrive_folder_id_text_input"
            )
            if raw_folder_id:
                cleaned_id = raw_folder_id.strip()
                if "drive.google.com" in cleaned_id:
                    import re
                    match = re.search(r'/folders/([a-zA-Z0-9-_]+)', cleaned_id)
                    if match:
                        cleaned_id = match.group(1)
                if "?" in cleaned_id:
                    cleaned_id = cleaned_id.split("?")[0]
                
                if st.session_state.get("gdrive_folder_id") != cleaned_id:
                    st.session_state.gdrive_folder_id = cleaned_id
                    st.rerun()
            
            gdrive_folder_id = st.session_state.get("gdrive_folder_id", env_folder_id)
                
            uploaded_cred = st.file_uploader(
                "구글 서비스 계정 키 (.json 파일) 등록:",
                type=["json"],
                help="Google Cloud Console에서 발급한 서비스 계정 키 JSON 파일을 업로드해 주세요.",
                key="gdrive_credential_file_uploader"
            )
            
            # Process uploaded JSON key
            if uploaded_cred:
                with open(GD_CREDS_FILE, "wb") as f:
                    f.write(uploaded_cred.getbuffer())
                st.toast("✅ 구글 서비스 계정 자격증명이 저장되었습니다.")
                st.rerun()
                
            # Derived Service Account info
            has_credentials = os.path.exists(GD_CREDS_FILE) or "GDRIVE_CREDS_JSON" in os.environ or "GDRIVE_CREDS_JSON" in st.secrets
            if has_credentials:
                try:
                    if "GDRIVE_CREDS_JSON" in st.secrets:
                        cred_data = st.secrets["GDRIVE_CREDS_JSON"]
                        if isinstance(cred_data, str):
                            cred_data = json.loads(cred_data)
                    elif "GDRIVE_CREDS_JSON" in os.environ:
                        cred_data = json.loads(os.environ["GDRIVE_CREDS_JSON"])
                    else:
                        with open(GD_CREDS_FILE, "r") as f:
                            cred_data = json.load(f)
                    client_email = cred_data.get("client_email", "")
                    
                    st.info(f"""
                    **구글 드라이브 폴더 사전 작업 필수 사항**
                    동기화할 구글 드라이브 폴더의 공유 설정에 아래 서비스 계정 이메일을 **편집자** 권한으로 꼭 추가해 주세요:
                    👉 `{client_email}`
                    """)
                except Exception as e:
                    st.error(f"구글 자격증명 파일 읽기 실패: {str(e)}")
        
        # Section B: 구글 드라이브에 새 파일 직접 업로드
        if has_credentials and gdrive_folder_id:
            st.markdown("")
            with st.container(border=True):
                st.markdown("#### 📤 구글 드라이브 파일 직접 업로드")
                st.write("웹 대시보드에서 드라이브로 파일을 업로드하면, RAG 임베딩 동기화까지 동시에 처리합니다.")
                
                gdrive_files = st.file_uploader(
                    "업로드할 문서 파일 선택:",
                    type=["txt", "md", "docx", "xlsx", "xls", "pdf", "hwpx"],
                    accept_multiple_files=True,
                    key="gdrive_direct_file_uploader"
                )
                
                if gdrive_files:
                    if not api_key:
                        st.warning("⚠️ 임베딩 분석을 위해 API Key 설정이 먼저 필요합니다.")
                    else:
                        if st.button("🚀 구글 드라이브로 업로드 및 동기화 실행", type="primary", use_container_width=True, key="btn_upload_sync"):
                            # Authenticate with Google Drive
                            try:
                                if "GDRIVE_CREDS_JSON" in st.secrets:
                                    cred_info = st.secrets["GDRIVE_CREDS_JSON"]
                                    if isinstance(cred_info, str):
                                        cred_info = json.loads(cred_info)
                                elif "GDRIVE_CREDS_JSON" in os.environ:
                                    cred_info = json.loads(os.environ["GDRIVE_CREDS_JSON"])
                                else:
                                    with open(GD_CREDS_FILE, "r") as f:
                                        cred_info = json.load(f)
                                service = gdrive_service.get_gdrive_service(cred_info)
                                
                                # Upload all selected files
                                upload_progress = st.progress(0)
                                upload_status = st.empty()
                                
                                for idx, f in enumerate(gdrive_files):
                                    upload_status.write(f"📤 `{f.name}` 구글 드라이브로 업로드 중... ({idx+1}/{len(gdrive_files)})")
                                    gdrive_service.upload_file_to_folder(
                                        service=service,
                                        folder_id=gdrive_folder_id,
                                        file_name=f.name,
                                        file_content=f.getvalue(),
                                        mime_type=f.type
                                    )
                                    upload_progress.progress((idx + 1) / len(gdrive_files))
                                
                                upload_status.write("✨ 구글 드라이브 업로드 완료! 데이터베이스 인덱싱을 동기화 중입니다...")
                                
                                # Immediately trigger full scan and sync
                                remote_files = gdrive_service.list_files_in_folder(service, gdrive_folder_id)
                                indexed_files = database.get_indexed_files()
                                
                                drive_files_state = {}
                                drive_metadata_map = {}
                                supported_exts = {'.txt', '.md', '.docx', '.xlsx', '.xls', '.pdf', '.hwpx', '.hwp'}
                                for rf in remote_files:
                                    rel_p = rf["rel_path"]
                                    ext = os.path.splitext(rel_p)[1].lower()
                                    if ext not in supported_exts:
                                        continue  # Skip unsupported files like Thumbs.db
                                    m_epoch = parse_rfc3339(rf["modifiedTime"])
                                    drive_files_state[rel_p] = m_epoch
                                    drive_metadata_map[rel_p] = rf
                                    
                                added, modified, deleted = calculate_sync_diff(drive_files_state, indexed_files)
                                total_actions = len(added) + len(modified) + len(deleted)
                                
                                if total_actions > 0:
                                    # Download files before RAG sync
                                    for download_idx, rel_p in enumerate(added + modified):
                                        upload_status.write(f"📥 구글 드라이브에서 파일 다운로드 중 ({download_idx+1}/{len(added+modified)}): `{rel_p}`...")
                                        file_info = drive_metadata_map[rel_p]
                                        local_dest = os.path.join(DOCS_DIR, rel_p)
                                        final_local_path = gdrive_service.download_file(service, file_info, local_dest)
                                        
                                        final_rel_p = os.path.relpath(final_local_path, DOCS_DIR).replace("\\", "/")
                                        if final_rel_p != rel_p:
                                            drive_files_state[final_rel_p] = drive_files_state.pop(rel_p)
                                            if rel_p in added:
                                                added[added.index(rel_p)] = final_rel_p
                                            if rel_p in modified:
                                                modified[modified.index(rel_p)] = final_rel_p
                                                
                                    sync_documents(api_key, added, modified, deleted, drive_files_state)
                                
                                # Backup DB to Google Drive
                                try:
                                    gdrive_service.upload_db_file(service, gdrive_folder_id, DB_PATH)
                                except Exception as backup_err:
                                    st.warning(f"⚠️ 업로드는 완료되었으나 DB 백업에 실패했습니다: {str(backup_err)}")
                                
                                st.rerun()
                            except Exception as e:
                                st.error(f"구글 드라이브 업로드/동기화 도중 오류 발생: {str(e)}")

        # Section C: 구글 드라이브 수동 동기화
        if has_credentials and gdrive_folder_id:
            st.markdown("")
            with st.container(border=True):
                st.markdown("#### 🔄 구글 드라이브 수동 동기화")
                st.write("클라우드 폴더의 변경사항(추가/수정/삭제)을 수동으로 스캔하여 지식베이스를 동기화합니다.")
                
                if not api_key:
                    st.info("💡 동기화를 실행하려면 사이드바에 Gemini API Key를 먼저 입력해 주세요.")
                else:
                    if st.button("🔄 구글 드라이브 변경사항 감지 및 동기화 실행", type="primary", use_container_width=True, key="btn_manual_sync"):
                        with st.spinner("구글 드라이브 API 스캔 및 인덱싱 처리 중..."):
                            try:
                                if "GDRIVE_CREDS_JSON" in st.secrets:
                                    cred_info = st.secrets["GDRIVE_CREDS_JSON"]
                                    if isinstance(cred_info, str):
                                        cred_info = json.loads(cred_info)
                                elif "GDRIVE_CREDS_JSON" in os.environ:
                                    cred_info = json.loads(os.environ["GDRIVE_CREDS_JSON"])
                                else:
                                    with open(GD_CREDS_FILE, "r") as f:
                                        cred_info = json.load(f)
                                service = gdrive_service.get_gdrive_service(cred_info)
                                
                                remote_files = gdrive_service.list_files_in_folder(service, gdrive_folder_id)
                                indexed_files = database.get_indexed_files()
                                
                                drive_files_state = {}
                                drive_metadata_map = {}
                                supported_exts = {'.txt', '.md', '.docx', '.xlsx', '.xls', '.pdf', '.hwpx', '.hwp'}
                                for rf in remote_files:
                                    rel_p = rf["rel_path"]
                                    ext = os.path.splitext(rel_p)[1].lower()
                                    if ext not in supported_exts:
                                        continue  # Skip unsupported files like Thumbs.db
                                    m_epoch = parse_rfc3339(rf["modifiedTime"])
                                    drive_files_state[rel_p] = m_epoch
                                    drive_metadata_map[rel_p] = rf
                                    
                                added, modified, deleted = calculate_sync_diff(drive_files_state, indexed_files)
                                total_actions = len(added) + len(modified) + len(deleted)
                                
                                if total_actions > 0:
                                    status_info = st.empty()
                                    
                                    for idx, rel_p in enumerate(added + modified):
                                        status_info.write(f"📥 구글 드라이브에서 파일 다운로드 중 ({idx+1}/{len(added+modified)}): `{rel_p}`...")
                                        file_info = drive_metadata_map[rel_p]
                                        local_dest = os.path.join(DOCS_DIR, rel_p)
                                        final_local_path = gdrive_service.download_file(service, file_info, local_dest)
                                        
                                        final_rel_p = os.path.relpath(final_local_path, DOCS_DIR).replace("\\", "/")
                                        if final_rel_p != rel_p:
                                            drive_files_state[final_rel_p] = drive_files_state.pop(rel_p)
                                            if rel_p in added:
                                                added[added.index(rel_p)] = final_rel_p
                                            if rel_p in modified:
                                                modified[modified.index(rel_p)] = final_rel_p
                                                
                                    status_info.empty()
                                    sync_documents(api_key, added, modified, deleted, drive_files_state)
                                    
                                    # Backup DB to Google Drive
                                    try:
                                        gdrive_service.upload_db_file(service, gdrive_folder_id, DB_PATH)
                                    except Exception as backup_err:
                                        st.warning(f"⚠️ 동기화는 완료되었으나 DB 백업에 실패했습니다: {str(backup_err)}")
                                    st.rerun()
                                else:
                                    st.success("✅ 구글 드라이브와 로컬 데이터베이스의 동기화 상태가 완벽히 일치합니다.")
                            except Exception as e:
                                st.error(f"구글 드라이브 동기화 도중 오류 발생: {str(e)}")
        else:
            st.warning("⚠️ 구글 서비스 계정 키(.json) 등록 및 드라이브 폴더 ID 입력이 완료되어야 동기화를 진행할 수 있습니다.")
                
    with col_right:
        with st.container(border=True):
            st.markdown("#### 🗄️ 현재 저장된 지식 목록 및 상세 관리")
            st.write("RAG 데이터베이스에 적재되어 있는 지식 조각들을 확인하고 개별 삭제를 관리합니다.")
            
            st.info("💡 **안내**: 문서의 삭제는 구글 드라이브에서 파일을 먼저 삭제한 뒤 왼쪽의 **동기화 실행**을 눌러 반영하는 것을 권장합니다.")
            
            if all_docs:
                df = pd.DataFrame(all_docs)
                df['category_kor'] = df['category'].map({'document': '문서 지식', 'qa_history': '피드백 학습'})
                
                st.dataframe(
                    df[['id', 'title', 'category_kor', 'created_at']],
                    column_config={
                        "id": "ID",
                        "title": "지식 조각 제목",
                        "category_kor": "유형",
                        "created_at": "등록 일자"
                    },
                    use_container_width=True,
                    hide_index=True
                )
                
                st.markdown("#### 🔍 지식 개별 상세 조회 및 삭제")
                selected_to_inspect = st.selectbox(
                    "조회할 지식을 선택해 주세요:",
                    options=all_docs,
                    format_func=lambda x: f"[{'문서' if x['category'] == 'document' else '피드백'}] {x['title']} (ID: {x['id']})",
                    key="sb_inspect_knowledge"
                )
                
                if selected_to_inspect:
                    st.markdown(f"**제목**: {selected_to_inspect['title']} | **등록일**: {selected_to_inspect['created_at']}")
                    st.text_area(
                        "텍스트 본문:",
                        value=selected_to_inspect['content'],
                        height=180,
                        disabled=True,
                        key=f"content_view_{selected_to_inspect['id']}"
                    )
                    if st.button("🗑️ 선택한 지식 삭제", type="secondary", use_container_width=True, key="btn_del_doc"):
                        database.delete_document(selected_to_inspect['id'])
                        if selected_to_inspect['category'] == 'document':
                            indexed_files = database.get_indexed_files()
                            for fname in indexed_files.keys():
                                if selected_to_inspect['title'].startswith(fname):
                                    database.remove_indexed_file_record(fname)
                                    break
                        st.success("해당 지식을 삭제했습니다.")
                        
                        # Backup DB to Google Drive
                        try:
                            gdrive_folder_id = st.secrets.get("gdrive_folder_id", os.environ.get("gdrive_folder_id", ""))
                            has_credentials = os.path.exists(GD_CREDS_FILE) or "GDRIVE_CREDS_JSON" in os.environ or "GDRIVE_CREDS_JSON" in st.secrets
                            if has_credentials and gdrive_folder_id:
                                if "GDRIVE_CREDS_JSON" in st.secrets:
                                    cred_info = st.secrets["GDRIVE_CREDS_JSON"]
                                    if isinstance(cred_info, str):
                                        cred_info = json.loads(cred_info)
                                elif "GDRIVE_CREDS_JSON" in os.environ:
                                    cred_info = json.loads(os.environ["GDRIVE_CREDS_JSON"])
                                else:
                                    with open(GD_CREDS_FILE, "r") as f:
                                        cred_info = json.load(f)
                                service = gdrive_service.get_gdrive_service(cred_info)
                                gdrive_service.upload_db_file(service, gdrive_folder_id, DB_PATH)
                        except Exception as backup_err:
                            st.warning(f"⚠️ 지식 삭제는 완료되었으나 DB 백업에 실패했습니다: {str(backup_err)}")
                            
                        st.rerun()
            else:
                st.info("현재 로컬 데이터베이스에 저장된 지식이 없습니다. 문서를 업로드해 주세요.")

# ==========================================
# Menu 3: 시스템 설정 및 가이드
# ==========================================
elif menu == "⚙️ 시스템 설정 및 가이드":
    st.markdown("### ⚙️ 시스템 가이드 및 사용자 권한 관리")
    st.markdown("---")
    
    col_guide, col_admin = st.columns([1, 1])
    
    with col_guide:
        with st.container(border=True):
            st.markdown("#### 📖 프로그램 작동 구조 안내")
            st.write("""
            본 프로그램은 **성장형 RAG (Retrieval-Augmented Generation)** 아키텍처에 기반하여 설계되었습니다.
            
            1. **다중 소스 동기화 (구글 드라이브)**
               - 연동된 구글 드라이브 폴더의 한글(`.hwpx`, `.hwp`), 엑셀(`.xlsx`, `.xls`), 워드(`.docx`), PDF(`.pdf`), 텍스트(`.txt`, `.md`) 파일 포맷을 모두 파싱하여 데이터베이스에 자동으로 임베딩 인덱싱합니다.
               
            2. **실시간 외부 기준 검토 (Google Search Grounding)**
               - 질문 내용 중 법령 기준이나 규정이 포함되어 있으면 AI가 구글 실시간 웹 검색을 사용하여 답변에 참고한 원본 링크들을 보여줍니다.
               
            3. **피드백 기반 자가 성장 루프**
               - AI 상담사가 작성한 내용 중 프로젝트에 최적화된 결과물을 '학습 피드백'으로 DB에 추가하면 차후 유사한 질문 시 최우선순위로 조회되어 상담 성능이 지속적으로 진화합니다.
            """)
            st.success("💡 **Tip**: 질문할 때 '고시 기준', '소방법령' 등의 키워드를 넣고 웹 검색 연동을 켜두면 더욱 정교한 답변을 받아보실 수 있습니다.")
        
    with col_admin:
        with st.container(border=True):
            st.markdown("#### 👥 사용자 계정 권한 관리 (Admin Panel)")
            
            if st.session_state.role == "admin":
                st.write("관리자 권한으로 시스템에 다른 사용자를 등록하거나 기존 계정을 삭제할 수 있습니다.")
                
                users_list = database.get_all_users()
                df_users = pd.DataFrame(users_list)
                st.dataframe(
                    df_users[['id', 'username', 'role', 'created_at']],
                    column_config={
                        "id": "ID",
                        "username": "아이디",
                        "role": "역할",
                        "created_at": "생성 시각"
                    },
                    use_container_width=True,
                    hide_index=True
                )
                
                st.markdown("##### ➕ 새 사용자 등록")
                with st.form("new_user_form", clear_on_submit=True):
                    new_username = st.text_input("새 사용자 ID:", placeholder="영문/숫자 조합")
                    new_password = st.text_input("새 사용자 비밀번호:", type="password", placeholder="비밀번호 입력")
                    new_role = st.selectbox("사용자 역할 권한:", options=["user", "admin"])
                    
                    if st.form_submit_button("사용자 등록 실행"):
                        if not new_username.strip() or not new_password.strip():
                            st.error("아이디와 비밀번호를 모두 입력해 주세요.")
                        else:
                            success = database.create_user(new_username.strip(), new_password.strip(), new_role)
                            if success:
                                st.success(f"사용자 `{new_username}` 계정이 정상적으로 생성되었습니다.")
                                st.rerun()
                            else:
                                st.error("이미 존재하는 사용자 아이디입니다.")
                                
                st.markdown("##### 🗑️ 사용자 계정 삭제")
                user_to_delete = st.selectbox(
                    "삭제할 계정 선택:",
                    options=[u["username"] for u in users_list if u["username"] != st.session_state.username],
                    key="sb_user_del"
                )
                if user_to_delete:
                    if st.button(f"🗑️ `{user_to_delete}` 계정 영구 삭제", key="btn_del_user"):
                        database.delete_user(user_to_delete)
                        st.success(f"계정 `{user_to_delete}`가 삭제되었습니다.")
                        st.rerun()
            else:
                st.info("🔒 사용자 관리 기능은 `admin` 계정으로 접속했을 때만 나타납니다. (현재 일반 사용자 권한)")
                
                st.markdown("##### 🔑 비밀번호 변경")
                with st.form("change_password_form", clear_on_submit=True):
                    curr_pass = st.text_input("현재 비밀번호 확인:", type="password")
                    new_pass = st.text_input("새 비밀번호:", type="password")
                    
                    if st.form_submit_button("비밀번호 변경 실행"):
                        if database.verify_user(st.session_state.username, curr_pass):
                            database.delete_user(st.session_state.username)
                            database.create_user(st.session_state.username, new_pass, st.session_state.role)
                            st.success("비밀번호가 안전하게 변경되었습니다. 다음 로그인 시 적용됩니다.")
                        else:
                            st.error("현재 비밀번호가 일치하지 않습니다.")

    # Diagnostic Section
    st.markdown("")
    with st.container(border=True):
        st.markdown("#### 🔌 API 연결 및 지원 모델 자가 진단")
        st.write("입력하신 Gemini API Key를 통해 실제로 어떤 모델들을 사용할 수 있는지 실시간 목록을 조회합니다.")
        
        if st.button("🔌 API 연결 및 모델 리스트 검사", use_container_width=True, key="btn_api_diagnostic"):
            api_key = st.session_state.get("gemini_api_key")
            if not api_key:
                st.error("사이드바에 API Key를 먼저 입력해 주세요.")
            else:
                with st.spinner("Gemini API에서 사용 가능한 모델 목록을 조회 중..."):
                    try:
                        import google.generativeai as genai
                        genai.configure(api_key=api_key)
                        models = list(genai.list_models())
                        
                        st.success("✅ API 연결 성공!")
                        
                        embed_models = []
                        gen_models = []
                        for m in models:
                            if 'embedContent' in m.supported_generation_methods or 'embed_content' in m.supported_generation_methods:
                                embed_models.append(m.name)
                            else:
                                gen_models.append(m.name)
                                
                        st.markdown("##### 🔹 임베딩 지원 모델 (Embedding Models):")
                        if embed_models:
                            for em in embed_models:
                                st.markdown(f"- `{em}`")
                        else:
                            st.warning("⚠️ 임베딩을 지원하는 모델이 목록에 없습니다! 계정의 API 권한을 검토하세요.")
                            
                        with st.expander("🔹 전체 모델 리스트 보기", expanded=False):
                            for m in models:
                                st.markdown(f"- **{m.name}** (메서드: `{m.supported_generation_methods}`)")
                    except Exception as e:
                        st.error(f"❌ API 호출 실패: {str(e)}")
