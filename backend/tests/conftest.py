"""测试全局配置。

- 保证测试离线、确定性、快速：禁用 BGE reranker 的 HuggingFace 网络加载
  （否则每个 Retriever 首次检索都要等 ~30s 超时后回退）。
- 生产默认 reranker="auto" 不受影响（settings 是模块级单例，仅测试进程内改写）。
"""

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.config import settings

settings.reranker = "none"
