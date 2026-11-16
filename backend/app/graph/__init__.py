# -*- coding: utf-8 -*-
"""LangGraph 法律咨询状态机。

四大铁律在图中的落点：
1. 每条结论必挂现行法条 —— retrieve 节点空证据走 insufficient_evidence 终止路径（证据不足，不幻觉）
2. 双视角对抗 —— adversarial_review 节点（adversarial=True 时启用）补「对方律师视角」
3. 时效感知 —— 检索层 STATUS_WEIGHT 降权 + Citation 携带 status/amended_history
4. 多法域 —— 全状态携带 jurisdiction，节点不写死国别

图拓扑：
    START → intake ──(拒绝/注入)──> END(refused)
              │
              ▼
        structure_facts → retrieve ──(无证据)──> END(insufficient_evidence)
                                  │
                                  ▼
                            generate_draft → nli_verify
                                              │
                              (降级且开人工确认)→ human_confirm ─┐
                                              │                  │
                                              ▼                  │
                                    adversarial_review ◄─────────┘
                                              │
                                              ▼
                                          finalize → END
"""
