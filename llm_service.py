import google.generativeai as genai
from typing import List, Dict, Any

def get_embedding(text: str, api_key: str) -> List[float]:
    """Generates text embedding using a supported embedding model.
    Includes self-healing fallback mechanisms to dynamically detect available models.
    """
    if not text.strip():
        return []
    
    genai.configure(api_key=api_key)
    
    # Preferred models
    preferred_models = ["models/gemini-embedding-001", "models/text-embedding-004", "models/embedding-001"]
    
    last_err = None
    for model_name in preferred_models:
        try:
            response = genai.embed_content(
                model=model_name,
                content=text,
                task_type="retrieval_document"
            )
            return response['embedding']
        except Exception as e:
            last_err = e
            continue
            
    # Auto-detection fallback
    try:
        available_embed_models = []
        for m in genai.list_models():
            if 'embedContent' in m.supported_generation_methods or 'embed_content' in m.supported_generation_methods:
                available_embed_models.append(m.name)
                
        if available_embed_models:
            # Sort to try text-embedding models first
            available_embed_models.sort(key=lambda x: "embedding" in x, reverse=True)
            fallback_model = available_embed_models[0]
            try:
                response = genai.embed_content(
                    model=fallback_model,
                    content=text,
                    task_type="retrieval_document"
                )
                return response['embedding']
            except Exception as final_err:
                raise RuntimeError(
                    f"임베딩 생성 오류. 자동 선택 모델 ({fallback_model}) 호출 실패: {str(final_err)}. "
                    f"API에서 조회된 사용 가능한 모델 목록: {available_embed_models}"
                )
        else:
            raise RuntimeError(
                f"임베딩 모델을 찾을 수 없습니다. 기본 시도 중 마지막 에러: {str(last_err)}"
            )
    except Exception as list_err:
        raise RuntimeError(
            f"임베딩 생성 실패: {str(last_err)}. (모델 목록 확인 실패: {str(list_err)})"
        )

def get_embeddings_batch(texts: List[str], api_key: str) -> List[List[float]]:
    """Generates embeddings for a list of texts in batches of 100 using models/gemini-embedding-001.
    Reduces API call count by 100x, vastly improving performance and avoiding rate limits.
    """
    if not texts:
        return []
        
    genai.configure(api_key=api_key)
    model_name = "models/gemini-embedding-001"
    
    all_embeddings = []
    batch_size = 100
    
    for i in range(0, len(texts), batch_size):
        batch_texts = texts[i:i+batch_size]
        try:
            response = genai.embed_content(
                model=model_name,
                content=batch_texts,
                task_type="retrieval_document"
            )
            # The API returns a list of embeddings in response['embedding']
            all_embeddings.extend(response['embedding'])
        except Exception as e:
            raise RuntimeError(
                f"일괄 임베딩 생성 중 오류 발생 (인덱스 {i}~{i+len(batch_texts)}): {str(e)}"
            )
            
    return all_embeddings



def generate_answer(
    query: str, 
    retrieved_docs: List[Dict[str, Any]], 
    chat_history: List[Dict[str, Any]], 
    api_key: str, 
    enable_search: bool = False,
    model_name: str = "gemini-2.0-flash"
) -> Dict[str, Any]:
    """Generates an answer using the Gemini API.
    Combines local database context, recent chat history, and optional Google Search Grounding.
    """
    genai.configure(api_key=api_key)
    
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

    # 4. Attempt to initialize and generate content with dynamic fallbacks
    candidates = [
        f"models/{model_name}" if not model_name.startswith("models/") else model_name,
        "models/gemini-2.5-flash",
        "models/gemini-3.5-flash",
        "models/gemini-flash-latest",
        "models/gemini-2.0-flash",
        "models/gemini-1.5-flash",
        "models/gemini-pro-latest"
    ]
    
    # Keep list unique and preserve order
    unique_candidates = []
    for c in candidates:
        if c not in unique_candidates:
            unique_candidates.append(c)
            
    last_err = None
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
                    # Fallback to no tools for this model if search tool is not supported
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
            
            # Succeeded! Parse sources and return
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
            continue
            
    # 5. If all preferred models fail, query available generation models
    try:
        available_gen_models = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods or 'generate_content' in m.supported_generation_methods:
                # Store the model name, e.g. models/gemini-1.5-flash
                available_gen_models.append(m.name)
                
        if available_gen_models:
            # Try to find a good fallback candidate
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
                raise RuntimeError(
                    f"모든 모델이 실패했으며, 자동 검색된 모델 ({fallback_candidate}) 호출도 실패했습니다: {str(final_err)}. "
                    f"API에서 사용 가능한 생성 모델 목록: {available_gen_models}"
                )
        else:
            raise RuntimeError(
                f"답변 생성 실패. 시도된 모델 중 마지막 에러: {str(last_err)}. "
                "API Key에서 사용 가능한 생성 모델을 찾을 수 없습니다."
            )
    except Exception as list_err:
        raise RuntimeError(
            f"답변 생성 실패: {str(last_err)}. (모델 목록 확인 실패: {str(list_err)})"
        )

