"""P1-8 多模态拍照咨询：OCR 识别 → 内容路由 → 对应分析流程。

路由规则（关键词启发式，P1 不引入分类模型）：
- 合同类（合同/协议/甲方乙方/违约金…）→ 合同风险扫描
- 事故类（事故/碰撞/责任认定/现场…）→ 案件事实结构化 + 侵权提示
- 诊断/医疗类（诊断证明/病历/医疗费…）→ 事实结构化 + 人身损害提示
- 聊天截图类（微信/聊天记录/转账…）→ 事实结构化（电子证据提示）
- 其他 → 事实结构化兜底

OCR 不可用时如实降级：返回明确的安装/替代指引，绝不假装识别成功。
"""

import re

from app.models.schemas import FactSet
from app.services.contract_service import ContractScanResponse, ContractScanService
from app.services.facts_service import structure_facts
from app.services.ocr_service import ocr_image

_ROUTE_RULES: list[tuple[str, re.Pattern]] = [
    ("contract", re.compile(r"合同|协议|甲方|乙方|违约金|定金|签署|签章|盖章")),
    ("accident", re.compile(r"事故|碰撞|撞|责任认定|现场|报警|肇事")),
    ("medical", re.compile(r"诊断|病历|医疗费|住院|伤残|出院|医嘱")),
    ("chat", re.compile(r"微信|聊天记录|转账记录|红包|截图|群聊")),
]


def route_content(text: str) -> str:
    for route, pattern in _ROUTE_RULES:
        if pattern.search(text):
            return route
    return "general"


class MultimodalService:
    def __init__(self, contract_service: ContractScanService):
        self.contract_service = contract_service

    def analyze(self, image_bytes: bytes) -> dict:
        ocr_text, backend = ocr_image(image_bytes)

        if ocr_text is None:
            return {
                "ok": False,
                "ocr_backend": backend,
                "error": (
                    "当前环境无可用 OCR 后端。可选方案：\n"
                    "1. pip install paddleocr pillow（推荐，支持中/日/韩/英）\n"
                    "2. pip install pytesseract 并安装 Tesseract-OCR + 语言包\n"
                    "3. 直接把图片内容粘贴到文本框走纯文本流程"
                ),
                "route": "none",
            }

        route = route_content(ocr_text)
        result: dict = {"ok": True, "ocr_backend": backend, "ocr_text": ocr_text, "route": route}

        if route == "contract":
            result["analysis"] = self.contract_service.scan(ocr_text).model_dump()
            result["route_label"] = "合同风险扫描"
        elif route == "accident":
            fs: FactSet = structure_facts(ocr_text)
            result["analysis"] = fs.model_dump()
            result["route_label"] = "案件事实结构化（侵权/事故）"
            result["hints"] = [
                "保存事故责任认定书、现场照片、医疗票据原件",
                "涉及人身损害的，治疗终结后及时做伤残等级鉴定",
            ]
        elif route == "medical":
            fs = structure_facts(ocr_text)
            result["analysis"] = fs.model_dump()
            result["route_label"] = "案件事实结构化（人身损害）"
            result["hints"] = [
                "医疗费主张需以正式票据为准；保留病历、诊断证明、费用清单",
                "误工费需收入证明；残疾赔偿金需伤残鉴定结论",
            ]
        elif route == "chat":
            fs = structure_facts(ocr_text)
            result["analysis"] = fs.model_dump()
            result["route_label"] = "案件事实结构化（电子证据）"
            result["hints"] = [
                "截图需保留原始载体（手机/电脑）以备当庭演示；重要聊天可申请公证保全",
                "转账记录建议下载官方电子回单而非仅用截图",
            ]
        else:
            fs = structure_facts(ocr_text)
            result["analysis"] = fs.model_dump()
            result["route_label"] = "案件事实结构化（通用）"

        return result
