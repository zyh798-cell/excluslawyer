# -*- coding: utf-8 -*-
"""法律知识图谱包：双 schema（大陆法系 + 普通法系判例子图）+ 可插拔后端。

- schema.py：节点/关系类型、Neo4j 约束、两套 schema 描述
- builder.py：种子概念 + 官方条文链接 + 跨法域 ANALOGOUS_TO（构建期校验 ID）
- backends.py：MemoryGraph（开箱即用）/ Neo4jGraphBackend（生产）
"""
