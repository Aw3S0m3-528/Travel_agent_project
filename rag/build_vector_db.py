import sys
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma

# 让脚本可以从项目根目录导入 tools
BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.append(str(BASE_DIR))

from tools.rag_tool import get_embeddings, VECTOR_DB_DIR, COLLECTION_NAME


load_dotenv()

RAW_DOC_DIR = BASE_DIR / "data" / "raw_docs"


def infer_city_from_filename(file_path: Path) -> str:
    """
    根据文件名简单推断城市。
    """
    name = file_path.stem.lower()

    city_map = {
        "chongqing": "重庆",
        "chengdu": "成都",
        "beijing": "北京",
        "xian": "西安",
        "hangzhou": "杭州",
        "tokyo": "东京",
    }

    return city_map.get(name, file_path.stem)


def load_documents():
    """
    加载 data/raw_docs 下的 txt 和 md 文件。
    """

    if not RAW_DOC_DIR.exists():
        raise FileNotFoundError(f"资料目录不存在：{RAW_DOC_DIR}")

    docs = []

    files = list(RAW_DOC_DIR.glob("*.txt")) + list(RAW_DOC_DIR.glob("*.md"))

    if not files:
        raise FileNotFoundError(f"没有在 {RAW_DOC_DIR} 中找到 txt 或 md 文件。")

    for file_path in files:
        text = file_path.read_text(encoding="utf-8")
        city = infer_city_from_filename(file_path)

        doc = Document(
            page_content=text,
            metadata={
                "source": str(file_path),
                "city": city,
                "filename": file_path.name
            }
        )
        docs.append(doc)

    return docs


def build_vector_db():
    """
    构建本地 Chroma 向量数据库。
    """

    print("正在加载旅游资料...")
    docs = load_documents()
    print(f"已加载原始文档数量：{len(docs)}")

    print("正在切分文本...")
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=80,
        separators=["\n\n", "\n", "。", "！", "？", ".", " ", ""]
    )

    chunks = splitter.split_documents(docs)
    print(f"切分后文本块数量：{len(chunks)}")

    print("正在创建 Gemini Embedding...")
    embeddings = get_embeddings()

    print("正在写入 Chroma 向量数据库...")
    VECTOR_DB_DIR.mkdir(parents=True, exist_ok=True)

    Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        collection_name=COLLECTION_NAME,
        persist_directory=str(VECTOR_DB_DIR)
    )

    print("向量数据库构建完成。")
    print(f"保存位置：{VECTOR_DB_DIR}")


if __name__ == "__main__":
    build_vector_db()