from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader

CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
SEPARATORS = ("\n\n", "\n", "。", "；", "，", " ")


def extract_text(file_name: str, content: bytes) -> str:
    suffix = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
    if suffix == "pdf":
        try:
            reader = PdfReader(BytesIO(content))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as exc:
            raise ValueError("无法读取 PDF，请确认文件未损坏且未加密") from exc
    elif suffix in {"txt", "md"}:
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                text = content.decode("gb18030")
            except UnicodeDecodeError as exc:
                raise ValueError("文本编码无法识别，请另存为 UTF-8 后重试") from exc
    else:
        raise ValueError("仅支持 PDF、TXT 和 Markdown 文件")

    text = text.replace("\x00", "").strip()
    if not text:
        raise ValueError("未能从文件中提取文字；扫描版 PDF 暂不支持 OCR")
    return text


def split_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split at paragraph/sentence boundaries where possible, with overlap."""
    if chunk_size <= 0 or overlap < 0 or overlap >= chunk_size:
        raise ValueError("Invalid chunking configuration")
    text = text.strip()
    if not text:
        return []

    chunks: list[str] = []
    start = 0
    length = len(text)
    while start < length:
        end = min(start + chunk_size, length)
        if end < length:
            lower_bound = start + max(1, chunk_size // 2)
            for separator in SEPARATORS:
                boundary = text.rfind(separator, lower_bound, end)
                if boundary >= lower_bound:
                    end = boundary + len(separator)
                    break

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= length:
            break
        start = max(start + 1, end - overlap)
    return chunks
