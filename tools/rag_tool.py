import os
from pathlib import Path
from typing import List, Dict, Any

from dotenv import load_dotenv


load_dotenv()

BASE_DIR = Path(__file__).resolve().parents[1]
VECTOR_DB_DIR = BASE_DIR / "data" / "vector_db" / "travel_chroma"
RAW_DOC_DIR = BASE_DIR / "data" / "raw_docs"
COLLECTION_NAME = "travel_knowledge"


def get_google_api_key() -> str:
    """
    获取 Gemini API Key。
    优先读取 GOOGLE_API_KEY。
    如果没有，则尝试读取 OPENAI_API_KEY。
    """
    api_key = os.getenv("GOOGLE_API_KEY", "").strip()

    if not api_key:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()

    if not api_key:
        raise ValueError("未配置 GOOGLE_API_KEY 或 OPENAI_API_KEY，无法使用 Gemini Embedding。")

    return api_key


def gemini_embedding_available() -> bool:
    return bool(os.getenv("GOOGLE_API_KEY", "").strip())


def vector_rag_enabled() -> bool:
    value = os.getenv("RAG_USE_VECTOR", "true").strip().lower()
    return value not in {"0", "false", "no", "off"}


def get_embeddings():
    """
    创建 Gemini Embedding 模型。
    """
    from langchain_google_genai import GoogleGenerativeAIEmbeddings

    api_key = get_google_api_key()
    model = os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001").strip()

    return GoogleGenerativeAIEmbeddings(
        model=model,
        google_api_key=api_key
    )


def get_vector_store():
    """
    加载本地 Chroma 向量数据库。
    """
    from langchain_chroma import Chroma

    embeddings = get_embeddings()

    return Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=embeddings,
        persist_directory=str(VECTOR_DB_DIR)
    )


def rag_db_exists() -> bool:
    """
    判断向量数据库是否已经存在。
    """
    return VECTOR_DB_DIR.exists() and any(VECTOR_DB_DIR.iterdir())


def tokenize_query(query: str) -> List[str]:
    separators = [" ", "，", "。", "、", ",", ".", "：", ":", "；", ";", "\n", "\t"]
    tokens = [query]

    for separator in separators:
        next_tokens = []
        for token in tokens:
            next_tokens.extend(token.split(separator))
        tokens = next_tokens

    return [
        token.strip()
        for token in tokens
        if len(token.strip()) >= 2
    ]


def infer_city_from_filename(file_path: Path) -> str:
    city_map = {
        "chongqing": "重庆",
        "chengdu": "成都",
        "beijing": "北京",
        "xian": "西安",
        "hangzhou": "杭州",
        "tokyo": "东京",
    }

    return city_map.get(file_path.stem.lower(), file_path.stem)


def keyword_retrieve_raw_docs(query: str, k: int = 5) -> List[Dict[str, Any]]:
    """
    Gemini Embedding 不可用时的本地关键词检索兜底。
    """

    if not RAW_DOC_DIR.exists():
        return []

    tokens = tokenize_query(query)
    files = list(RAW_DOC_DIR.glob("*.txt")) + list(RAW_DOC_DIR.glob("*.md"))
    scored_docs = []

    for file_path in files:
        text = file_path.read_text(encoding="utf-8")
        score = 0

        for token in tokens:
            if token in text:
                score += text.count(token)

        if score <= 0:
            continue

        excerpt = text[:1200]
        scored_docs.append({
            "score": score,
            "content": excerpt,
            "metadata": {
                "source": str(file_path),
                "city": infer_city_from_filename(file_path),
                "retrieval": "keyword_fallback"
            }
        })

    scored_docs.sort(key=lambda item: item["score"], reverse=True)

    return [
        {
            "content": item["content"],
            "metadata": item["metadata"]
        }
        for item in scored_docs[:k]
    ]


def retrieve_travel_info(query: str, k: int = 5) -> List[Dict[str, Any]]:
    """
    从旅游知识库中检索相关资料。
    """

    if not vector_rag_enabled():
        print("RAG：RAG_USE_VECTOR=false，使用本地关键词检索兜底。")
        return keyword_retrieve_raw_docs(query, k=k)

    if not rag_db_exists():
        return keyword_retrieve_raw_docs(query, k=k)

    if not gemini_embedding_available():
        print("RAG：未配置 GOOGLE_API_KEY，使用本地关键词检索兜底。")
        return keyword_retrieve_raw_docs(query, k=k)

    try:
        vector_store = get_vector_store()

        docs = vector_store.similarity_search(query, k=k)
    except Exception as exc:
        print(f"RAG：向量检索失败，使用本地关键词检索兜底。错误信息：{exc}")
        return keyword_retrieve_raw_docs(query, k=k)

    results = []

    for doc in docs:
        results.append({
            "content": doc.page_content,
            "metadata": doc.metadata
        })

    return results


def format_rag_results(results: List[Dict[str, Any]]) -> str:
    """
    将 RAG 检索结果整理成文本，方便交给 Agent。
    """

    if not results:
        return "未从本地 RAG 知识库中检索到相关资料。"

    context_parts = []

    for index, item in enumerate(results, start=1):
        metadata = item.get("metadata", {})
        source = metadata.get("source", "未知来源")
        city = metadata.get("city", "未知城市")

        context_parts.append(
            f"【资料{index}】\n"
            f"来源：{source}\n"
            f"城市：{city}\n"
            f"内容：{item.get('content', '')}"
        )

    return "\n\n".join(context_parts)
