import os
import json
import re
from typing import Any, Dict, Optional
import time

from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()


DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash"


def get_llm_api_key() -> str:
    return (
        os.getenv("DEEPSEEK_API_KEY", "").strip()
        or os.getenv("OPENAI_API_KEY", "").strip()
    )


def get_llm_base_url() -> str:
    base_url = os.getenv("OPENAI_BASE_URL", "").strip()

    if base_url:
        return base_url

    if os.getenv("DEEPSEEK_API_KEY", "").strip():
        return DEEPSEEK_BASE_URL

    return ""


def get_llm_model() -> str:
    return (
        os.getenv("DEEPSEEK_MODEL", "").strip()
        or os.getenv("OPENAI_MODEL", "").strip()
        or (DEFAULT_DEEPSEEK_MODEL if os.getenv("DEEPSEEK_API_KEY", "").strip() else "")
    )


def llm_available() -> bool:
    """
    判断是否已经配置大模型 API。
    如果没有配置，就使用规则版 Agent 兜底。
    """
    api_key = get_llm_api_key()
    model = get_llm_model()
    return bool(api_key and model)


def get_llm_client() -> OpenAI:
    """
    创建 OpenAI-compatible 客户端。
    如果 OPENAI_BASE_URL 为空，则默认使用官方接口。
    如果填写 OPENAI_BASE_URL，则使用兼容接口。
    """
    api_key = get_llm_api_key()
    base_url = get_llm_base_url()

    if not api_key:
        raise ValueError("未配置 OPENAI_API_KEY 或 DEEPSEEK_API_KEY")

    if base_url:
        return OpenAI(api_key=api_key, base_url=base_url)

    return OpenAI(api_key=api_key)


def call_llm(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.3,
    max_tokens: int = 2000,
    retry: int = 2
) -> str:
    """
    调用大语言模型。
    如果遇到 503 / 高负载问题，自动重试几次。
    """
    model = get_llm_model()

    if not model:
        raise ValueError("未配置 OPENAI_MODEL 或 DEEPSEEK_MODEL")

    client = get_llm_client()

    last_error = None

    for attempt in range(retry + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                messages=[
                    {
                        "role": "system",
                        "content": system_prompt
                    },
                    {
                        "role": "user",
                        "content": user_prompt
                    }
                ]
            )

            content = response.choices[0].message.content

            if content is None:
                return ""

            return content.strip()

        except Exception as e:
            last_error = e
            print(f"LLM 调用失败，第 {attempt + 1} 次，错误信息：{e}")

            if attempt < retry:
                wait_seconds = 2 * (attempt + 1)
                print(f"等待 {wait_seconds} 秒后重试...")
                time.sleep(wait_seconds)

    raise last_error


def extract_json(text: str) -> Optional[Dict[str, Any]]:
    """
    从大模型输出中提取 JSON。
    有些模型可能会输出 ```json ... ```，这里做兼容处理。
    """
    if not text:
        return None

    text = text.strip()

    # 去除 markdown 代码块
    text = re.sub(r"^```json", "", text)
    text = re.sub(r"^```", "", text)
    text = re.sub(r"```$", "", text)
    text = text.strip()

    # 优先直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 再尝试从文本中提取第一个 JSON 对象
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None

    return None
