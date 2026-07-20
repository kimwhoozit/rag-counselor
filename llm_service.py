import time
import random
import google.generativeai as genai
from typing import List, Dict, Any

def get_working_keys(api_key):
    """Helper to convert a string or a list of API keys into a list of non-empty strings."""
    if isinstance(api_key, str):
        return [api_key.strip()] if api_key.strip() else []
    elif isinstance(api_key, list):
        return [k.strip() for k in api_key if k and k.strip()]
    return []

def get_embedding(text: str, api_key) -> List[float]:
    """Generates text embedding using a supported embedding model.
    Includes fallback mechanisms and key rotation for rate/quota limits.
    """
    if not text.strip():
        return []
    
    keys = get_working_keys(api_key)
    if not keys:
        raise ValueError("API Key가 설정되어 있지 않습니다.")
        
    preferred_models = ["models/gemini-embedding-001", "models/text-embedding-004", "models/embedding-001"]
    max_retries = 3
    base_delay = 2.0
    
    last_err = None
    
    # Try each configured API Key
    for active_key in keys:
        genai.configure(api_key=active_key)
        
        for model_name in preferred_models:
            for attempt in range(max_retries):
                try:
                    response = genai.embed_content(
                        model=model_name,
                        content=text,
                        task_type="retrieval_document"
                    )
                    return response['embedding']
                except Exception as e:
                    last_err = e
                    err_msg = str(e).lower()
                    # Quota / Rate limit error
                    if "429" in err_msg or "quota" in err_msg or "rate limit" in err_msg or "resource_exhausted" in err_msg:
                        if active_key != keys[-1]:
                            break  # Skip to the next API key immediately
                        else:
                            # Last key: backoff and retry
                            sleep_time = (base_delay ** attempt) + random.uniform(0, 1)
                            time.sleep(sleep_time)
                    else:
                        break  # Non-quota error, try next model
            
            # If rate limit hit and it wasn't the last key, we broke the inner loop.
            # Check if we should switch keys immediately.
            err_msg = str(last_err).lower()
            if ("429" in err_msg or "quota" in err_msg or "rate limit" in err_msg or "resource_exhausted" in err_msg) and active_key != keys[-1]:
                break
                
        err_msg = str(last_err).lower()
        if ("429" in err_msg or "quota" in err_msg or "rate limit" in err_msg or "resource_exhausted" in err_msg) and active_key != keys[-1]:
            continue

    # Fallback to listing models if preferred ones fail (trying all keys)
    for active_key in keys:
        genai.configure(api_key=active_key)
        try:
            available_embed_models = []
            for m in genai.list_models():
                if 'embedContent' in m.supported_generation_methods or 'embed_content' in m.supported_generation_methods:
                    available_embed_models.append(m.name)
                    
            if available_embed_models:
                available_embed_models.sort(key=lambda x: "embedding" in x, reverse=True)
                fallback_model = available_embed_models[0]
                
                for attempt in range(max_retries):
                    try:
                        response = genai.embed_content(
                            model=fallback_model,
                            content=text,
                            task_type="retrieval_document"
                        )
                        return response['embedding']
                    except Exception as final_err:
                        last_err = final_err
                        err_msg = str(final_err).lower()
                        if "429" in err_msg or "quota" in err_msg or "rate limit" in err_msg or "resource_exhausted" in err_msg:
                            if active_key != keys[-1]:
                                break  # try next key
                            else:
                                sleep_time = (base_delay ** attempt) + random.uniform(0, 1)
                                time.sleep(sleep_time)
                        else:
                            break
        except Exception as list_err:
            last_err = list_err
            
    raise RuntimeError(
        f"임베딩 생성 실패: 모든 API Key의 할당량이 초과되었거나 오류가 발생했습니다. 최종 오류: {str(last_err)}"
    )

def get_embeddings_batch(texts: List[str], api_key) -> List[List[float]]:
    """Generates embeddings for a list of texts in batches of 100 using models/gemini-embedding-001.
    Reduces API call count and rotates API keys upon hitting rate/quota limits.
    """
    if not texts:
        return []
        
    keys = get_working_keys(api_key)
    if not keys:
        raise ValueError("API Key가 설정되어 있지 않습니다.")
        
    model_name = "models/gemini-embedding-001"
    all_embeddings = []
    batch_size = 100
    
    max_retries = 5
    base_delay = 3.0
    
    current_key_idx = 0
    
    for i in range(0, len(texts), batch_size):
        batch_texts = texts[i:i+batch_size]
        success = False
        last_err = None
        
        while current_key_idx < len(keys):
            active_key = keys[current_key_idx]
            genai.configure(api_key=active_key)
            
            success = False
            for attempt in range(max_retries):
                try:
                    response = genai.embed_content(
                        model=model_name,
                        content=batch_texts,
                        task_type="retrieval_document"
                    )
                    all_embeddings.extend(response['embedding'])
                    success = True
                    time.sleep(0.5)
                    break
                except Exception as e:
                    last_err = e
                    err_msg = str(e).lower()
                    if "429" in err_msg or "quota" in err_msg or "rate limit" in err_msg or "resource_exhausted" in err_msg:
                        if current_key_idx < len(keys) - 1:
                            print(f"Embedding batch key {current_key_idx+1} quota exceeded. Switching to key {current_key_idx+2}...")
                            current_key_idx += 1
                            break  # try next key in while loop
                        else:
                            # Last key: backoff and retry
                            sleep_time = (base_delay ** attempt) + random.uniform(0, 1.5)
                            sleep_time = min(sleep_time, 60.0)
                            time.sleep(sleep_time)
                    else:
                        time.sleep(1.0)
                        
            if success:
                break
            if not success and current_key_idx == len(keys) - 1:
                break
                
        if not success:
            raise RuntimeError(
                f"일괄 임베딩 생성 중 오류 발생 (인덱스 {i}~{i+len(batch_texts)}) - 모든 API Key의 할당량이 소진되었거나 오류가 발생했습니다. 최종 오류: {str(last_err)}"
            )
            
    return all_embeddings

def generate_answer(
    query: str, 
    retrieved_docs: List[Dict[str, Any]], 
    chat_history: List[Dict[str, Any]], 
    api_key, 
    enable_search: bool = False,
    model_name: str = "gemini-2.0-flash"
) -> Dict[str, Any]:
    """Generates an answer using the Gemini API.
    Supports API key rotation when encountering rate/quota limit errors.
    """
    keys = get_working_keys(api_key)
    if not keys:
        raise ValueError("API Key가 설정되어 있지 않습니다.")
        
    # 1. Build Document Context
    doc_context_parts = []
    qa_context_parts = []
    
    for doc in retrieved_docs:
        category = doc.get("category", "document")
        title = doc.get("title", "Unknown")
        content = doc.get("content", "")
        score = doc.get("score", 0.0)
        
        if category == "qa_history":
            qa_context_parts.append(
                f"[이전 질문 상황]: {title}\n"
                f"[이전 답변 내용 (유사도: {score:.2f})]:\n{content}\n"
                "-----------------------------------"
            )
        else:
            doc_context_parts.append(
                f"[문서명: {title} (유사도: {score:.2f})]:\n{content}\n"
                "-----------------------------------"
            )
            
    doc_context = "\n".join(doc_context_parts) if doc_context_parts else "참고할 수 있는 문서가 로컬 데이터베이스에 없습니다."
    qa_context = "\n".join(qa_context_parts) if qa_context_parts else "참고할 수 있는 이전 성장형 상담 답변이 없습니다."
    
    # 2. Build Recent Session Chat History Context (limit to last 6 messages)
    history_context = ""
    if chat_history:
        recent_history = chat_history[-6:]
        history_context = "\n".join([
            f"{'사용자' if msg['role'] == 'user' else 'AI 상담사'}: {msg['message']}" 
            for msg in recent_history
        ])
    else:
        history_context = "최근 대화 내역 없음."
    
    # 3. Define System Instruction
    system_instruction = (
        "당신은 프로젝트 관리 및 시설 기준, 법령 검토를 도와주는 전문적이고 성장형인 AI 상담사입니다.\n"
        "제공된 [참고 문서]와 [이전 질문 상황 및 답변 내용]을 바탕으로 사용자의 질문에 정확하고 성실하게 답변해 주세요.\n"
        "실시간 법규나 개정된 고시 등 외부 최신 자료가 필요하고 웹 검색 도구가 활성화되어 있다면 검색 결과를 적극 참고하여 답변에 반영해 주세요.\n"
        "답변 작성 규칙:\n"
        "1. 질문과 가장 관련성 높은 내부 자료(참고 문서)의 핵심 내용을 성실하게 반영합니다.\n"
        "2. 과거 상담사 답변([이전 질문 상황 및 답변 내용])에 매칭되는 해결 사례가 있으면, 과거 사례를 언급하며 일관성 있는 지침을 제공합니다.\n"
        "3. 웹 검색으로 수집된 정보와 내부 지식이 불일치하면(예: 법률 개정), 그 차이점을 상세히 지적하고 비교 설명해 줍니다.\n"
        "4. 답변 시 참고한 로컬 문서명이나 웹 검색 출처 링크(제공 시)를 명확히 밝힙니다.\n"
        "5. 한국어로 매우 친절하고 전문적인 톤앤매너로 성의 있게 상세히 답변해 주세요."
    )
    
    # Formulate Prompt
    prompt = f"""
[로컬 데이터베이스 검색 결과]
=== 1. 참고 문서 (프로젝트 관련 서류) ===
{doc_context}

=== 2. 이전 질문 상황 및 답변 내용 ===
{qa_context}

[현재 세션 최근 대화 기록]
{history_context}

[사용자의 새로운 질문]
사용자: {query}
AI 상담사:
"""

    # Attempt to initialize and generate content with dynamic fallbacks
    candidates = [
        f"models/{model_name}" if not model_name.startswith("models/") else model_name,
        "models/gemini-2.5-flash",
        "models/gemini-3.5-flash",
        "models/gemini-flash-latest",
        "models/gemini-2.0-flash",
        "models/gemini-1.5-flash",
        "models/gemini-pro-latest"
    ]
    
    unique_candidates = []
    for c in candidates:
        if c not in unique_candidates:
            unique_candidates.append(c)
            
    last_err = None
    
    # Try with each API key in order
    for active_key in keys:
        genai.configure(api_key=active_key)
        
        for candidate in unique_candidates:
            try:
                model = None
                current_enable_search = enable_search
                if current_enable_search:
                    try:
                        model = genai.GenerativeModel(
                            model_name=candidate,
                            system_instruction=system_instruction,
                            tools=['google_search']
                        )
                    except Exception:
                        model = genai.GenerativeModel(
                            model_name=candidate,
                            system_instruction=system_instruction
                        )
                        current_enable_search = False
                else:
                    model = genai.GenerativeModel(
                        model_name=candidate,
                        system_instruction=system_instruction
                    )
                    
                response = model.generate_content(prompt)
                
                sources = []
                try:
                    if current_enable_search and hasattr(response, 'candidates') and response.candidates:
                        cand = response.candidates[0]
                        if hasattr(cand, 'grounding_metadata') and cand.grounding_metadata:
                            metadata = cand.grounding_metadata
                            if hasattr(metadata, 'grounding_chunks') and metadata.grounding_chunks:
                                for chunk in metadata.grounding_chunks:
                                    if hasattr(chunk, 'web') and chunk.web:
                                        sources.append({
                                            "title": chunk.web.title,
                                            "uri": chunk.web.uri
                                        })
                except Exception:
                    pass
                    
                return {
                    "answer": response.text,
                    "sources": sources
                }
            except Exception as e:
                last_err = e
                err_msg = str(e).lower()
                # If quota exceeded and there are other keys left, switch to next key immediately
                if ("429" in err_msg or "quota" in err_msg or "rate limit" in err_msg or "resource_exhausted" in err_msg) and active_key != keys[-1]:
                    break  # breaks candidate loop to try next key in keys loop
                else:
                    continue  # try next candidate with same key
                    
        # Check if we broke because of quota, then continue keys loop
        err_msg = str(last_err).lower()
        if ("429" in err_msg or "quota" in err_msg or "rate limit" in err_msg or "resource_exhausted" in err_msg) and active_key != keys[-1]:
            continue

    # Fallback to querying list of models using keys rotation
    for active_key in keys:
        genai.configure(api_key=active_key)
        try:
            available_gen_models = []
            for m in genai.list_models():
                if 'generateContent' in m.supported_generation_methods or 'generate_content' in m.supported_generation_methods:
                    available_gen_models.append(m.name)
                    
            if available_gen_models:
                fallback_candidate = available_gen_models[0]
                for m_name in available_gen_models:
                    if "1.5-flash" in m_name or "pro" in m_name:
                        fallback_candidate = m_name
                        break
                
                try:
                    fallback_model = genai.GenerativeModel(
                        model_name=fallback_candidate,
                        system_instruction=system_instruction
                    )
                    response = fallback_model.generate_content(prompt)
                    return {
                        "answer": response.text,
                        "sources": []
                    }
                except Exception as final_err:
                    last_err = final_err
        except Exception as list_err:
            last_err = list_err
            
    raise RuntimeError(
        f"답변 생성 실패: 모든 API Key의 할당량이 초과되었거나 오류가 발생했습니다. 최종 오류: {str(last_err)}"
    )
