from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
PROMPT_DIR = BASE_DIR / "prompts"


def load_prompt(filename: str) -> str:
    """
    从 prompts 目录读取提示词文件。
    """

    prompt_path = PROMPT_DIR / filename

    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt 文件不存在：{prompt_path}")

    return prompt_path.read_text(encoding="utf-8").strip()
