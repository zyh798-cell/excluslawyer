# -*- coding: utf-8 -*-
"""图谱 schema：分两套——大陆法系（中/日/韩成文法）+ 普通法系（新加坡判例子图）。

节点统一用 `node_type` 属性区分，Neo4j label 与 node_type 一一对应；
`id` 全局唯一（约束按 label 建）。
"""

# ---- 节点类型 → Neo4j Label ----
NODE_LABELS: dict[str, str] = {
    # 大陆法系（成文法）
    "concept": "Concept",  # 法律概念（违约责任/侵权责任/……）
    "element": "Element",  # 构成要件
    "duty": "Duty",  # 责任方式/法律后果
    "period": "Period",  # 期间
    "statute": "Statute",  # 成文法条文（CN/JP/KR/SG 均有）
    # 普通法系（新加坡判例子图）
    "precedent": "Precedent",  # 判例
    "principle": "Principle",  # 裁判规则/要旨
    "court": "Court",  # 法院
}

# ---- 关系类型 ----
# 大陆法系
REL_CONCEPT_ELEMENT = "构成要件"
REL_CONCEPT_DUTY = "责任方式"
REL_CONCEPT_PERIOD = "期间"
REL_BASIS = "依据条文"  # 概念/责任方式/期间 → 条文
REL_ANALOGOUS = "ANALOGOUS_TO"  # 跨法域对应条文（铁律④）
# 普通法系
REL_ESTABLISHES = "ESTABLISHES"  # 判例 → 裁判规则
REL_FOLLOWS = "FOLLOWS"  # 判例 → 判例（遵循先例）
REL_OVERRULES = "OVERRULES"  # 判例 → 判例（推翻）

REL_TYPES = [
    REL_CONCEPT_ELEMENT,
    REL_CONCEPT_DUTY,
    REL_CONCEPT_PERIOD,
    REL_BASIS,
    REL_ANALOGOUS,
    REL_ESTABLISHES,
    REL_FOLLOWS,
    REL_OVERRULES,
]

# ---- Neo4j 约束/索引（init_schema 用）----
CONSTRAINT_CYPHERS: list[str] = [
    f"CREATE CONSTRAINT kg_{label.lower()}_id IF NOT EXISTS "
    f"FOR (n:{label}) REQUIRE n.id IS UNIQUE"
    for label in NODE_LABELS.values()
]

# ---- 两套 schema 的机器可读描述（生成文档/校验用）----
CIVIL_SCHEMA = {
    "name": "大陆法系成文法 schema（CN/JP/KR 复用）",
    "node_types": ["concept", "element", "duty", "period", "statute"],
    "relations": [REL_CONCEPT_ELEMENT, REL_CONCEPT_DUTY, REL_CONCEPT_PERIOD, REL_BASIS, REL_ANALOGOUS],
    "pattern": "Concept -构成要件-> Element；Concept -责任方式-> Duty；"
    "Concept/Duty/Period -依据条文-> Statute；Statute -ANALOGOUS_TO-> Statute（跨法域）",
}

COMMON_SCHEMA = {
    "name": "普通法系判例子图（SG 独立子图）",
    "node_types": ["precedent", "principle", "court", "statute"],
    "relations": [REL_ESTABLISHES, REL_FOLLOWS, REL_OVERRULES, REL_BASIS],
    "pattern": "Precedent -ESTABLISHES-> Principle；Precedent -FOLLOWS-> Precedent；"
    "Principle -依据条文-> Statute（SG 成文规则）",
}
