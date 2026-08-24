from pathlib import Path
import fitz

MAX_FILE_SIZE = 10 * 1024 * 1024
MAX_PAGES = 20


async def save_and_parse_pdf(upload, upload_dir: str) -> tuple[str, str]:
    if not upload.filename or not upload.filename.lower().endswith(".pdf"):
        raise ValueError("仅支持 PDF 简历")
    data = await upload.read()
    if not data or len(data) > MAX_FILE_SIZE:
        raise ValueError("简历为空或超过 10MB 限制")
    target_dir = Path(upload_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"resume_{__import__('uuid').uuid4().hex}.pdf"
    path = target_dir / safe_name
    path.write_bytes(data)
    try:
        document = fitz.open(stream=data, filetype="pdf")
        if document.page_count > MAX_PAGES:
            raise ValueError("简历页数超过 20 页限制")
        text = "\n".join(page.get_text() for page in document).strip()
    except Exception as exc:
        path.unlink(missing_ok=True)
        raise ValueError("PDF 无法解析或已损坏") from exc
    if len(text) < 30:
        path.unlink(missing_ok=True)
        raise ValueError("未从 PDF 中提取到足够的简历文本")
    return str(path), text
