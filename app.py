import os
import json
import streamlit as st
import pandas as pd
import tempfile
import shutil
from datetime import datetime
import importlib
import database
importlib.reload(database)
import llm_service
importlib.reload(llm_service)
import utils
importlib.reload(utils)
import gdrive_service
importlib.reload(gdrive_service)

# 1. Page Configuration & Theme
st.set_page_config(
    page_title="프로젝트 성장형 AI 상담사",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize Database & Attempt Recovery if missing
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "knowledge_base.db")
GD_CREDS_FILE = os.path.join(BASE_DIR, "gdrive_credentials.json")
DOCS_DIR = os.path.join(BASE_DIR, "documents")
SECRETS_PATH = os.path.join(BASE_DIR, ".streamlit", "secrets.toml")

# Manual secrets fallback loader (in case Streamlit is run from parent directory)
manual_secrets = {}
if os.path.exists(SECRETS_PATH):
    try:
        import toml
        manual_secrets = toml.load(SECRETS_PATH)
    except Exception as e:
        print(f"⚠️ [Startup] secrets.toml 수동 로드 실패: {e}")

def get_secret(key, default=None):
    """Retrieves secret from Streamlit secrets, manual secrets fallback, or environment variables."""
    if key in st.secrets:
        return st.secrets[key]
    if key in manual_secrets:
        return manual_secrets[key]
    return os.environ.get(key, default)

def has_secret(key):
    """Checks if secret exists in st.secrets, manual secrets, or environment variables."""
    return key in st.secrets or key in manual_secrets or key in os.environ

if "db_recovery_status" not in st.session_state:
    st.session_state.db_recovery_status = "ok"

if not os.path.exists(DB_PATH):
    # Try to download from Google Drive
    gdrive_folder_id = get_secret("gdrive_folder_id", "")
    has_credentials = os.path.exists(GD_CREDS_FILE) or has_secret("GDRIVE_CREDS_JSON")
    if has_credentials and gdrive_folder_id:
        try:
            if has_secret("GDRIVE_CREDS_JSON"):
                cred_info = get_secret("GDRIVE_CREDS_JSON")
                if isinstance(cred_info, str):
                    cred_info = json.loads(cred_info)
            else:
                with open(GD_CREDS_FILE, "r") as f:
                    cred_info = json.load(f)
            service = gdrive_service.get_gdrive_service(cred_info)
            success = gdrive_service.download_db_file(service, gdrive_folder_id, DB_PATH)
            if success:
                st.session_state.db_recovery_status = "success"
                print("✅ [Startup] 구글 드라이브로부터 백업 DB 복구 성공!")
            else:
                st.session_state.db_recovery_status = "not_found"
                print("⚠️ [Startup] 구글 드라이브에 백업 DB(knowledge_base.db) 파일이 존재하지 않습니다.")
        except Exception as e:
            st.session_state.db_recovery_status = f"error: {str(e)}"
            print(f"❌ [Startup] 구글 드라이브 DB 복구 중 에러 발생: {str(e)}")
    else:
        st.session_state.db_recovery_status = "no_credentials"
        print("⚠️ [Startup] 구글 드라이브 연동 설정(자격증명 또는 폴더 ID)이 누락되어 백업 DB 복구를 건너뜁니다.")

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
if "gemini_api_key" not in st.session_state:
    st.session_state.gemini_api_key = get_secret("GEMINI_API_KEY", "")
if "gemini_api_key_sub1" not in st.session_state:
    st.session_state.gemini_api_key_sub1 = get_secret("GEMINI_API_KEY_SUB1", "")
if "gemini_api_key_sub2" not in st.session_state:
    st.session_state.gemini_api_key_sub2 = get_secret("GEMINI_API_KEY_SUB2", "")
if "openai_api_key" not in st.session_state:
    st.session_state.openai_api_key = get_secret("OPENAI_API_KEY", "")
if "anthropic_api_key" not in st.session_state:
    st.session_state.anthropic_api_key = get_secret("ANTHROPIC_API_KEY", "")

def get_all_api_keys():
    """Helper to return a list of active API keys in priority order."""
    keys = []
    for k in ["gemini_api_key", "gemini_api_key_sub1", "gemini_api_key_sub2"]:
        val = st.session_state.get(k, "")
        if val and val.strip():
            keys.append(val.strip())
    if not keys:
        for k in ["GEMINI_API_KEY", "GEMINI_API_KEY_SUB1", "GEMINI_API_KEY_SUB2"]:
            env_val = get_secret(k, "")
            if env_val and env_val.strip():
                keys.append(env_val.strip())
    return keys

def has_any_api_key():
    """Returns True if at least one API key is configured."""
    return len(get_all_api_keys()) > 0
if "sync_queue" not in st.session_state:
    st.session_state.sync_queue = None
if "sync_index" not in st.session_state:
    st.session_state.sync_index = 0

# Try to extract client_email for UI display and troubleshooting
if "client_email" not in st.session_state:
    st.session_state.client_email = "알 수 없음 (자격증명 미등록)"
    try:
        has_credentials = os.path.exists(GD_CREDS_FILE) or has_secret("GDRIVE_CREDS_JSON")
        if has_credentials:
            if has_secret("GDRIVE_CREDS_JSON"):
                cred_data = get_secret("GDRIVE_CREDS_JSON")
                if isinstance(cred_data, str):
                    cred_data = json.loads(cred_data)
            else:
                with open(GD_CREDS_FILE, "r") as f:
                    cred_data = json.load(f)
            st.session_state.client_email = cred_data.get("client_email", "")
    except Exception:
        pass

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
    
    /* 기본 본문 패딩 초기화 */
    div.block-container {
        padding-top: 3rem !important;
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
                    # 기본 API Key 백엔드에 강제 주입 (일반 사용자 RAG 질문/검색 실패 방지)
                    st.session_state.gemini_api_key = get_secret("GEMINI_API_KEY", "")
                    st.session_state.openai_api_key = get_secret("OPENAI_API_KEY", "")
                    st.session_state.anthropic_api_key = get_secret("ANTHROPIC_API_KEY", "")
                    st.success("로그인 성공!")
                    st.rerun()
                else:
                    st.error("❌ 아이디 또는 비밀번호가 올바르지 않습니다.")
            

    st.stop()

# Helper constants
# Already defined as absolute paths relative to BASE_DIR at the top

# Utility functions
def handle_backup_error(error_obj):
    err_str = str(error_obj)
    if "storageQuotaExceeded" in err_str or "storage quota" in err_str.lower():
        email_addr = st.session_state.get("client_email", "서비스 계정 이메일")
        st.error(f"""
        ⚠️ **구글 드라이브 백업 실패 (스토리지 용량 초과)**
        
        구글 서비스 계정(Service Account)은 기본적으로 0바이트의 개인 스토리지만을 가집니다. 따라서 개인 폴더에는 파일을 직접 백업(소유)하여 생성할 수 없습니다.
        
        **해결 방법 (공유 드라이브 권장)**:
        1. 구글 드라이브에서 개인 폴더 대신 **'공유 드라이브(Shared Drive)'**를 새로 생성합니다.
        2. 생성한 공유 드라이브의 멤버 공유 설정에 아래 서비스 계정 이메일을 **콘텐츠 관리자** 또는 **편집자** 권한으로 추가합니다:
           👉 `{email_addr}`
        3. 해당 공유 드라이브 내에 폴더를 만들어 그 폴더 ID를 대시보드(또는 `secrets.toml`)에 입력하고 다시 동기화를 시도해 주세요.
        """)
    else:
        st.warning(f"⚠️ 데이터베이스 백업에 실패했습니다: {err_str}")

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
            content = utils.parse_file(full_path, api_key)
            chunks = utils.split_text(content)
            if not chunks:
                raise ValueError("파싱된 텍스트 내용이 비어 있습니다. (스캔 문서이거나 파싱 불가능한 형식)")
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
            if "sync_errors" in st.session_state:
                st.session_state.sync_errors.append({"file": rel_path, "error": str(e)})
            
        current_step += 1
        progress_bar.progress(current_step / total_steps)
        
    # 3. Process additions
    for rel_path in added:
        status_text.write(f"⚙️ `{rel_path}` 신규 임베딩 분석 중...")
        full_path = os.path.join(DOCS_DIR, rel_path)
        try:
            content = utils.parse_file(full_path, api_key)
            chunks = utils.split_text(content)
            if not chunks:
                raise ValueError("파싱된 텍스트 내용이 비어 있습니다. (스캔 문서이거나 파싱 불가능한 형식)")
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
            if "sync_errors" in st.session_state:
                st.session_state.sync_errors.append({"file": rel_path, "error": str(e)})
            
        current_step += 1
        progress_bar.progress(current_step / total_steps)
        
    status_text.write("✨ 동기화가 성공적으로 완료되었습니다!")
    st.toast("✅ 동기화 완료!", icon="🎉")


def parse_and_embed_single_file(api_key, file_path, rel_path):
    """Parses a single file and adds it to the database with its embedding chunks."""
    content = utils.parse_file(file_path, api_key)
    chunks = utils.split_text(content)
    if not chunks:
        raise ValueError("파싱된 텍스트 내용이 비어 있습니다. (스캔 문서이거나 파싱 불가능한 형식)")
    embeddings = llm_service.get_embeddings_batch(chunks, api_key)
    for c_idx, chunk in enumerate(chunks):
        database.add_document(
            title=f"{rel_path} (조각 {c_idx+1})",
            content=chunk,
            category="document",
            embedding=embeddings[c_idx]
        )


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
if "sync_errors" not in st.session_state:
    st.session_state.sync_errors = []

# Reload past chat messages from DB into Session State if empty
if not st.session_state.messages:
    db_history = database.get_chat_history(st.session_state.session_id)
    st.session_state.messages = db_history

# 2. Sidebar Layout (Options Panel)
with st.sidebar:
    st.markdown('<div style="font-size: 1.5rem; font-weight: 800; background: linear-gradient(90deg, #3b82f6 0%, #10b981 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin-bottom: 1rem;">🌱 프로젝트 상담사</div>', unsafe_allow_html=True)
    
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

    # API Configuration
    env_api_key = get_secret("GEMINI_API_KEY", "")
    env_sub1 = get_secret("GEMINI_API_KEY_SUB1", "")
    env_sub2 = get_secret("GEMINI_API_KEY_SUB2", "")
    env_openai_key = get_secret("OPENAI_API_KEY", "")
    env_anthropic_key = get_secret("ANTHROPIC_API_KEY", "")
    
    st.markdown("#### 🔑 API Key 설정")
    
    # Gemini API Keys (Only basic is restricted to admin, sub keys are visible to all)
    if st.session_state.role == "admin":
        api_key_input = st.text_input(
            "Gemini API Key (기본):",
            type="password",
            value=st.session_state.get("gemini_api_key", env_api_key),
            help="Google AI Studio에서 발급받은 기본 Gemini API Key를 입력하세요.",
            key="gdrive_api_key_input"
        )
        if api_key_input:
            st.session_state.gemini_api_key = api_key_input
            
    api_key_sub1_input = st.text_input(
        "Gemini API Key (보조 1):",
        type="password",
        value=st.session_state.get("gemini_api_key_sub1", env_sub1),
        help="기본 키 할당량 초과 시 사용할 첫 번째 보조 API Key입니다.",
        key="gdrive_api_key_sub1_input"
    )
    if api_key_sub1_input:
        st.session_state.gemini_api_key_sub1 = api_key_sub1_input
        
    api_key_sub2_input = st.text_input(
        "Gemini API Key (보조 2):",
        type="password",
        value=st.session_state.get("gemini_api_key_sub2", env_sub2),
        help="첫 번째 보조 키까지 초과 시 사용할 두 번째 보조 API Key입니다.",
        key="gdrive_api_key_sub2_input"
    )
    if api_key_sub2_input:
        st.session_state.gemini_api_key_sub2 = api_key_sub2_input

    # OpenAI & Anthropic API Keys (Visible to all users to configure their own keys)
    openai_key_input = st.text_input(
        "OpenAI API Key (ChatGPT용):",
        type="password",
        value=st.session_state.get("openai_api_key", env_openai_key),
        help="ChatGPT 모델(gpt-4o 등)을 사용할 때 필요한 OpenAI API Key를 입력하세요.",
        key="gdrive_openai_api_key_input"
    )
    if openai_key_input:
        st.session_state.openai_api_key = openai_key_input
        
    anthropic_key_input = st.text_input(
        "Anthropic API Key (Claude용):",
        type="password",
        value=st.session_state.get("anthropic_api_key", env_anthropic_key),
        help="Claude 모델(claude-3-5-sonnet 등)을 사용할 때 필요한 Anthropic API Key를 입력하세요.",
        key="gdrive_anthropic_api_key_input"
    )
    if anthropic_key_input:
        st.session_state.anthropic_api_key = anthropic_key_input
        
    st.markdown("---")
    
    # Model Configuration
    st.markdown("#### ⚙️ 추론 모델 설정")
    selected_model = st.selectbox(
        "추론 LLM 모델 선택:",
        options=["gemini-2.5-flash", "gemini-3.5-flash", "gemini-1.5-flash", "gemini-1.5-pro", "gpt-4o", "gpt-4o-mini", "claude-3-5-sonnet", "claude-3-5-haiku"],
        index=0,
        help="추론 성능과 속도에 맞는 모델을 선택합니다.",
        key="sb_model_selector"
    )
    st.markdown("---")

# 3. Main Dashboard Layout Header
st.markdown('<div class="main-title">🌱 프로젝트 상담사</div>', unsafe_allow_html=True)

# DB 복구 상태 진단 및 경고 출력
if st.session_state.get("db_recovery_status") == "not_found":
    st.warning("⚠️ **시스템 안내**: 구글 드라이브 폴더 내에 기존 백업 DB(`knowledge_base.db`) 파일이 존재하지 않습니다. 새로운 데이터베이스로 동작을 시작합니다. '구글 드라이브 지식 관리' 메뉴에서 동기화를 진행하여 백업을 활성화해주세요.")
elif st.session_state.get("db_recovery_status") == "no_credentials":
    st.info("💡 **알림**: 구글 드라이브 연동용 자격증명(JSON) 또는 폴더 ID 설정이 누락되어 자동 백업 DB 복구를 진행하지 못했습니다. 로컬 환경에 저장된 기존 DB로 계속 진행하거나, 시스템 설정 파일(`secrets.toml`)을 확인해주세요.")
elif isinstance(st.session_state.get("db_recovery_status"), str) and st.session_state.db_recovery_status.startswith("error:"):
    err_msg = st.session_state.db_recovery_status.replace("error: ", "")
    st.error(f"❌ **데이터베이스 복구 실패**: 구글 드라이브 백업 DB를 가져오는 중 오류가 발생했습니다. (오류 메시지: `{err_msg}`). 로컬 DB가 초기화되었을 수 있으니 구글 드라이브 권한 및 네트워크 연결 상태를 확인해주세요.")
elif st.session_state.get("db_recovery_status") == "success":
    st.success("✅ **보안 복구 완료**: 장기 미사용으로 유실되었던 로컬 데이터베이스를 구글 드라이브의 최신 백업본에서 안전하게 복구하였습니다.")
    # 한 번 성공 메시지를 보여준 뒤, 재렌더링 시에는 메시지가 사라지도록 상태를 변경합니다.
    st.session_state.db_recovery_status = "ok"

st.markdown("---")

# Horizontal Navigation Menu (Segmented Control)
menu = st.segmented_control(
    "📍 메뉴 이동",
    options=["💬 서류 검토 및 상담 (RAG)", "📚 구글 드라이브 지식 관리", "⚙️ 시스템 설정 및 가이드"],
    default="💬 서류 검토 및 상담 (RAG)",
    label_visibility="collapsed"
)
st.markdown("---")

# ==========================================
# Menu 1: 대화 및 서류 검토
# ==========================================
if menu == "💬 서류 검토 및 상담 (RAG)":
    # Warning check
    if not has_any_api_key():
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
        if enable_search and any(m in selected_model for m in ["gpt", "claude"]):
            st.caption("ℹ️ **안내**: 실시간 웹 검색(Google Search) 연동은 Gemini 모델에서만 지원됩니다. 현재 모델로 답변을 생성하나 웹 검색은 생략됩니다.")
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
                    api_keys = get_all_api_keys()
                    if not api_keys:
                        st.error("Gemini API Key가 누락되었습니다. 임베딩(지식베이스 검색) 및 기본 작동을 위해 Gemini API Key가 기본적으로 필요합니다. 왼쪽 상단 ⚙️ 설정에서 API Key를 설정해 주세요.")
                        st.stop()
                        
                    openai_api_key = st.session_state.get("openai_api_key", "").strip() or get_secret("OPENAI_API_KEY", "")
                    anthropic_api_key = st.session_state.get("anthropic_api_key", "").strip() or get_secret("ANTHROPIC_API_KEY", "")
                    
                    if selected_model.startswith("gpt-") and not openai_api_key:
                        st.error("OpenAI API Key가 누락되었습니다. 왼쪽 상단 ⚙️ 설정에서 OpenAI API Key를 입력해 주세요.")
                        st.stop()
                    elif selected_model.startswith("claude-") and not anthropic_api_key:
                        st.error("Anthropic API Key가 누락되었습니다. 왼쪽 상단 ⚙️ 설정에서 Anthropic API Key를 입력해 주세요.")
                        st.stop()
                        
                    # 2. Vector DB search (generate query embedding first)
                    query_embedding = llm_service.get_embedding(prompt, api_keys)
                    # Search documents in both category
                    retrieved_docs = database.search_similar_documents(query_embedding, limit=5)
                    
                    # 3. Model Generation
                    result = llm_service.generate_answer(
                        query=prompt,
                        retrieved_docs=retrieved_docs,
                        chat_history=st.session_state.messages[:-1], # pass previous history
                        api_key=api_keys,
                        openai_api_key=openai_api_key,
                        anthropic_api_key=anthropic_api_key,
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
                    api_keys = get_all_api_keys()
                    if api_keys:
                        with st.spinner("학습 답변 분석 및 지식 인덱싱 생성 중..."):
                            try:
                                combined_text = f"상황/질문: {learn_title}\n검토된 모범 답변: {st.session_state.last_response['answer']}"
                                emb = llm_service.get_embedding(combined_text, api_keys)
                                
                                database.add_document(
                                    title=learn_title,
                                    content=st.session_state.last_response['answer'],
                                    category="qa_history",
                                    embedding=emb
                                )
                                st.success("지식베이스에 학습 완료되었습니다! 다음 질문 검토 시 적극 참조됩니다.")
                                
                                # Backup DB to Google Drive
                                try:
                                    gdrive_folder_id = get_secret("gdrive_folder_id", "")
                                    has_credentials = os.path.exists(GD_CREDS_FILE) or has_secret("GDRIVE_CREDS_JSON")
                                    if has_credentials and gdrive_folder_id:
                                        if has_secret("GDRIVE_CREDS_JSON"):
                                            cred_info = get_secret("GDRIVE_CREDS_JSON")
                                            if isinstance(cred_info, str):
                                                cred_info = json.loads(cred_info)
                                        else:
                                            with open(GD_CREDS_FILE, "r") as f:
                                                cred_info = json.load(f)
                                        service = gdrive_service.get_gdrive_service(cred_info)
                                        gdrive_service.upload_db_file(service, gdrive_folder_id, DB_PATH)
                                except Exception as backup_err:
                                    handle_backup_error(backup_err)
                                
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
        api_key = get_all_api_keys()
        
        # Section A: 구글 드라이브 연동 설정 카드
        with st.container(border=True):
            st.markdown("#### ☁️ 구글 드라이브 연동 설정")
            st.write("구글 클라우드 서비스 계정 키(JSON)와 동기화할 폴더 ID를 설정합니다.")
            
            # Google Drive configuration inputs
            env_folder_id = get_secret("gdrive_folder_id", "")
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
            has_credentials = os.path.exists(GD_CREDS_FILE) or has_secret("GDRIVE_CREDS_JSON")
            if has_credentials:
                try:
                    if has_secret("GDRIVE_CREDS_JSON"):
                        cred_data = get_secret("GDRIVE_CREDS_JSON")
                        if isinstance(cred_data, str):
                            cred_data = json.loads(cred_data)
                    else:
                        with open(GD_CREDS_FILE, "r") as f:
                            cred_data = json.load(f)
                    client_email = cred_data.get("client_email", "")
                    
                    st.info(f"""
                    **구글 드라이브 폴더 사전 작업 필수 사항**
                    동기화할 구글 드라이브 폴더의 공유 설정에 아래 서비스 계정 이메일을 **편집자** 권한으로 꼭 추가해 주세요.
                    **서비스 계정 이메일:** `{client_email}`
                    """)
                except Exception as e:
                    st.error(f"구글 서비스 계정 자격증명 파싱 실패: {str(e)}")
            
        # Section B: 구글 드라이브 백업 DB 복구
        if has_credentials and gdrive_folder_id:
            st.markdown("")
            with st.container(border=True):
                st.markdown("#### 📥 구글 드라이브 백업 DB 복구")
                st.write("구글 드라이브에 저장된 최신 백업 `knowledge_base.db` 파일을 다운로드하여 로컬 DB를 덮어씁니다.")
                if st.button("📥 백업 DB 다운로드 실행 (기존 로컬 DB 덮어쓰기)", type="secondary", use_container_width=True, key="btn_download_db_gd"):
                    with st.spinner("구글 드라이브로부터 백업 DB 다운로드 중..."):
                        try:
                            if has_secret("GDRIVE_CREDS_JSON"):
                                cred_info = get_secret("GDRIVE_CREDS_JSON")
                                if isinstance(cred_info, str):
                                    cred_info = json.loads(cred_info)
                            else:
                                with open(GD_CREDS_FILE, "r") as f:
                                    cred_info = json.load(f)
                            service = gdrive_service.get_gdrive_service(cred_info)
                            success = gdrive_service.download_db_file(service, gdrive_folder_id, DB_PATH)
                            if success:
                                st.success("✅ 구글 드라이브로부터 백업 DB를 성공적으로 다운로드하여 적용했습니다!")
                                st.toast("✅ DB 복구 완료!", icon="🎉")
                                st.rerun()
                            else:
                                st.error("❌ 구글 드라이브에 백업 DB(`knowledge_base.db`) 파일이 존재하지 않습니다.")
                        except Exception as e:
                            st.error(f"❌ DB 복구 중 에러 발생: {str(e)}")
                            
        # Section C: 구글 드라이브 수동 동기화
        if has_credentials and gdrive_folder_id:
            st.markdown("")
            with st.container(border=True):
                st.markdown("#### 🔄 구글 드라이브 수동 동기화")
                st.write("클라우드 폴더의 변경사항(추가/수정/삭제)을 수동으로 스캔하여 지식베이스를 동기화합니다.")
                
                if not api_key:
                    st.info("💡 동기화를 실행하려면 사이드바에 Gemini API Key를 먼저 입력해 주세요.")
                else:
                    # 1. 동기화 대기/진행 큐가 세션에 존재할 때 진행바 및 추가 진행 버튼 표시
                    if st.session_state.sync_queue is not None:
                        total_tasks = len(st.session_state.sync_queue["tasks"])
                        current_idx = st.session_state.sync_index
                        st.warning(f"⏳ **동기화 작업 진행 중**: 총 `{total_tasks}`개의 변경 파일이 있습니다. (현재 진행률: `{current_idx} / {total_tasks}`)")
                        st.progress(current_idx / total_tasks if total_tasks > 0 else 1.0)
                        
                        # Initialize sync_active if not present
                        if "sync_active" not in st.session_state:
                            st.session_state.sync_active = True

                        col_action1, col_action2 = st.columns([1, 1])
                        with col_action1:
                            if st.session_state.sync_active:
                                if st.button("⏸️ 자동 동기화 일시 정지", use_container_width=True, key="btn_pause_sync_gd"):
                                    st.session_state.sync_active = False
                                    st.rerun()
                            else:
                                if st.button("▶️ 자동 동기화 시작/재개", type="primary", use_container_width=True, key="btn_resume_sync_gd"):
                                    st.session_state.sync_active = True
                                    st.rerun()
                        with col_action2:
                            if st.button("🚫 동기화 작업 강제 취소", type="secondary", use_container_width=True, key="btn_cancel_sync_gd"):
                                st.session_state.sync_queue = None
                                st.session_state.sync_index = 0
                                st.session_state.sync_active = False
                                st.toast("동기화 작업이 취소되었습니다.")
                                st.rerun()

                        if not st.session_state.sync_active:
                            st.info("⏸️ 자동 동기화 진행이 일시 정지되었습니다. 재개하려면 위의 시작/재개 버튼을 눌러주세요.")

                        if st.session_state.sync_active and current_idx < total_tasks:
                            with st.spinner("100개 배치 동기화 처리 중..."):
                                try:
                                    if has_secret("GDRIVE_CREDS_JSON"):
                                        cred_info = get_secret("GDRIVE_CREDS_JSON")
                                        if isinstance(cred_info, str):
                                            cred_info = json.loads(cred_info)
                                    else:
                                        with open(GD_CREDS_FILE, "r") as f:
                                            cred_info = json.load(f)
                                    service = gdrive_service.get_gdrive_service(cred_info)
                                    
                                    batch_tasks = st.session_state.sync_queue["tasks"][current_idx : current_idx + 100]
                                    progress_sync = st.progress(0)
                                    status_sync = st.empty()
                                    
                                    for b_idx, task in enumerate(batch_tasks):
                                        rel_p = task["path"]
                                        action = task["action"]
                                        status_sync.write(f"⚙️ ({b_idx+1}/{len(batch_tasks)}) `{rel_p}` 동기화 진행 중 ({action})...")
                                        
                                        if action == "delete":
                                            database.delete_document_by_title_prefix(rel_p)
                                            database.remove_indexed_file_record(rel_p)
                                            local_path = os.path.join(DOCS_DIR, rel_p)
                                            if os.path.exists(local_path):
                                                try: os.remove(local_path)
                                                except Exception: pass
                                        elif action in ("add", "modify"):
                                            file_info = st.session_state.sync_queue["drive_metadata_map"][rel_p]
                                            local_dest = os.path.join(DOCS_DIR, rel_p)
                                            
                                            def process_single_task():
                                                final_local_path = gdrive_service.download_file(service, file_info, local_dest)
                                                final_rel_p = os.path.relpath(final_local_path, DOCS_DIR).replace("\\", "/")
                                                database.delete_document_by_title_prefix(final_rel_p)
                                                database.remove_indexed_file_record(final_rel_p)
                                                parse_and_embed_single_file(api_key, final_local_path, final_rel_p)
                                                return final_rel_p

                                            import concurrent.futures
                                            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                                                future = executor.submit(process_single_task)
                                                try:
                                                    final_rel_p = future.result(timeout=300.0)
                                                    mtime = st.session_state.sync_queue["drive_files_state"].get(rel_p, datetime.now().timestamp())
                                                    database.mark_file_indexed(final_rel_p, mtime)
                                                except concurrent.futures.TimeoutError:
                                                    st.warning(f"⚠️ `{rel_p}` 파일 처리가 300초 동안 응답이 없어 다음 파일로 건너뜁니다.")
                                                    st.session_state.sync_errors.append({
                                                        "file": rel_p,
                                                        "error": "300초 타임아웃 초과 (대용량 문서 혹은 API 지연)"
                                                    })
                                                except Exception as parse_err:
                                                    st.error(f"오류 발생 ({rel_p}): {str(parse_err)}")
                                                    st.session_state.sync_errors.append({
                                                        "file": rel_p,
                                                        "error": str(parse_err)
                                                    })
                                        
                                        progress_sync.progress((b_idx + 1) / len(batch_tasks))
                                        
                                    status_sync.empty()
                                    st.session_state.sync_index += len(batch_tasks)
                                    
                                    try:
                                        gdrive_service.upload_db_file(service, gdrive_folder_id, DB_PATH)
                                    except Exception as backup_err:
                                        handle_backup_error(backup_err)

                                    if st.session_state.sync_index >= total_tasks:
                                        st.session_state.sync_queue = None
                                        st.session_state.sync_index = 0
                                        st.session_state.sync_active = False
                                        st.success("✨ 전체 구글 드라이브 동기화가 성공적으로 끝났습니다!")
                                        st.toast("🎉 동기화 전체 완료!", icon="✅")
                                        st.rerun()
                                    else:
                                        st.success(f"이번 배치 분량 동기화 완료! ({st.session_state.sync_index} / {total_tasks})")
                                        st.info("⏰ 3초 후 다음 100개 동기화 작업을 자동으로 시작합니다...")
                                        import time
                                        time.sleep(3)
                                        st.rerun()
                                except Exception as e:
                                    st.error(f"동기화 진행 도중 오류 발생: {str(e)}")
                                    st.session_state.sync_active = False
                                    st.rerun()
                    else:
                        # 2. 대기 큐가 없을 때, 구글 드라이브 변경 감지 실행 버튼 제공
                        if st.button("🔄 구글 드라이브 변경사항 감지 및 동기화 실행", type="primary", use_container_width=True, key="btn_manual_sync"):
                            with st.spinner("구글 드라이브 API 스캔 처리 중..."):
                                try:
                                    if has_secret("GDRIVE_CREDS_JSON"):
                                        cred_info = get_secret("GDRIVE_CREDS_JSON")
                                        if isinstance(cred_info, str):
                                            cred_info = json.loads(cred_info)
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
                                            continue
                                        m_epoch = parse_rfc3339(rf["modifiedTime"])
                                        drive_files_state[rel_p] = m_epoch
                                        drive_metadata_map[rel_p] = rf
                                        
                                    added, modified, deleted = calculate_sync_diff(drive_files_state, indexed_files)
                                    
                                    # 평탄화된 단일 태스크 빌드
                                    tasks = []
                                    for p in deleted:
                                        tasks.append({"action": "delete", "path": p})
                                    for p in added:
                                        tasks.append({"action": "add", "path": p})
                                    for p in modified:
                                        tasks.append({"action": "modify", "path": p})
                                        
                                    if len(tasks) > 0:
                                        st.session_state.sync_queue = {
                                            "tasks": tasks,
                                            "drive_files_state": drive_files_state,
                                            "drive_metadata_map": drive_metadata_map
                                        }
                                        st.session_state.sync_index = 0
                                        st.session_state.sync_active = True
                                        st.session_state.sync_errors = []
                                        st.rerun()
                                    else:
                                        st.success("✅ 구글 드라이브와 로컬 데이터베이스의 동기화 상태가 완벽히 일치합니다.")
                                except Exception as e:
                                    st.error(f"구글 드라이브 동기화 도중 오류 발생: {str(e)}")
                                    
                    # 동기화 오류 발생 현황 표시
                    if st.session_state.get("sync_errors"):
                        st.markdown("---")
                        st.markdown("##### ❌ 인베딩 실패 문서 현황")
                        st.warning("아래 파일들은 인베딩 과정에서 누락되었습니다. 사유를 확인 후 조치해 주세요.")
                        err_df = pd.DataFrame(st.session_state.sync_errors)
                        st.dataframe(
                            err_df,
                            column_config={
                                "file": "파일명 (경로)",
                                "error": "실패 사유"
                            },
                            use_container_width=True,
                            hide_index=True
                        )
                        if st.button("🧹 실패 기록 지우기", use_container_width=True, key="btn_clear_sync_errors"):
                            st.session_state.sync_errors = []
                            st.rerun()
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
                            gdrive_folder_id = get_secret("gdrive_folder_id", "")
                            has_credentials = os.path.exists(GD_CREDS_FILE) or has_secret("GDRIVE_CREDS_JSON")
                            if has_credentials and gdrive_folder_id:
                                if has_secret("GDRIVE_CREDS_JSON"):
                                    cred_info = get_secret("GDRIVE_CREDS_JSON")
                                    if isinstance(cred_info, str):
                                        cred_info = json.loads(cred_info)
                                else:
                                    with open(GD_CREDS_FILE, "r") as f:
                                        cred_info = json.load(f)
                                service = gdrive_service.get_gdrive_service(cred_info)
                                gdrive_service.upload_db_file(service, gdrive_folder_id, DB_PATH)
                        except Exception as backup_err:
                            handle_backup_error(backup_err)
                            
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
            api_keys = get_all_api_keys()
            if not api_keys:
                st.error("사이드바에 API Key를 먼저 입력해 주세요.")
            else:
                for idx, active_key in enumerate(api_keys):
                    st.markdown(f"### 🔑 API Key #{idx+1} ({active_key[:6]}...{active_key[-4:] if len(active_key) > 10 else ''}) 진단 결과:")
                    with st.spinner(f"Gemini API Key #{idx+1}에서 사용 가능한 모델 목록을 조회 중..."):
                        try:
                            import google.generativeai as genai
                            genai.configure(api_key=active_key)
                            models = list(genai.list_models())
                            
                            st.success(f"✅ API Key #{idx+1} 연결 성공!")
                            
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
                            st.error(f"❌ API Key #{idx+1} 연결 실패: {str(e)}")
