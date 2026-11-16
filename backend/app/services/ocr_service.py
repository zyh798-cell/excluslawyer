"""P1-8 OCR 适配层：可插拔后端（paddleocr / tesseract / none）。

优先级：PaddleOCR（中日韩英效果最好）→ pytesseract → 均无则返回 None，
由调用方降级提示"请安装 OCR 依赖或直接粘贴文本"。
"""

import logging

logger = logging.getLogger(__name__)


def detect_backend() -> str:
    """探测可用 OCR 后端。"""
    try:
        import paddleocr  # noqa: F401

        return "paddleocr"
    except ImportError:
        pass
    try:
        import pytesseract  # noqa: F401

        return "tesseract"
    except ImportError:
        pass
    return "none"


def ocr_image(image_bytes: bytes) -> tuple[str | None, str]:
    """识别图片文字，返回 (文本, 后端名)。识别不了返回 (None, backend)。"""
    backend = detect_backend()
    if backend == "none":
        return None, "none"

    try:
        if backend == "paddleocr":
            import io

            from paddleocr import PaddleOCR

            ocr = PaddleOCR(use_angle_cls=True, lang="ch")  # ch 模型覆盖中日韩英
            import numpy as np
            from PIL import Image

            img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            result = ocr.ocr(np.asarray(img))
            lines = []
            for page in result or []:
                for item in page or []:
                    if item and len(item) > 1:
                        lines.append(item[1][0])
            return "\n".join(lines), "paddleocr"

        if backend == "tesseract":
            import io

            import pytesseract
            from PIL import Image

            img = Image.open(io.BytesIO(image_bytes))
            # tesseract 多语言：chi_sim+eng 等；未装语言包时自动回退 eng
            try:
                text = pytesseract.image_to_string(img, lang="chi_sim+eng")
            except Exception:  # noqa: BLE001
                text = pytesseract.image_to_string(img)
            return text, "tesseract"
    except Exception as exc:  # noqa: BLE001
        logger.warning("OCR 识别失败（%s）: %s", backend, exc)
        return None, backend

    return None, backend
