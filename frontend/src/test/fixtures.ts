import type {
  Citation,
  ConsultGraphResponse,
  FactSet,
  KgQueryResponse,
  OpinionResponse,
} from "@/lib/api";

export const CITATION: Citation = {
  statute_id: "CN-MINFA-577",
  law_title: "中华人民共和国民法典",
  article_no: "第五百七十七条",
  text: "当事人一方不履行合同义务或者履行合同义务不符合约定的，应当承担继续履行、采取补救措施或者赔偿损失等违约责任。",
  gloss: "",
  jurisdiction: "CN",
  language: "zh",
  effective_status: "effective",
  effective_date: "2021-01-01",
  amended_history: ["2020-05-28 通过"],
  score: 0.9,
  source_url: "https://flk.npc.gov.cn/",
};

export const FACT_SET: FactSet = {
  facts: [
    { text: "公司拖欠三个月工资", fact_type: "confirmed", date_label: "2024-01" },
    { text: "打算离职并索赔", fact_type: "claim", date_label: null },
    { text: "如果协商不成", fact_type: "assumption", date_label: null },
    { text: "据说还有加班费争议", fact_type: "to_verify", date_label: null },
  ],
  timeline: [
    { date_label: "2024-01", sort_key: "2024-01", event_text: "公司拖欠三个月工资", fact_type: "confirmed" },
    { date_label: "待定", sort_key: "9999", event_text: "打算离职并索赔", fact_type: "claim" },
  ],
  counts: { confirmed: 1, to_verify: 1, assumption: 1, claim: 1 },
};

export const OPINION: OpinionResponse = {
  sections: [
    { title: "一、事实认定", content: "公司拖欠工资事实初步成立。", citation_ids: [] },
    { title: "二、法律适用", content: "适用劳动合同法相关条文。", citation_ids: ["CN-MINFA-577"] },
  ],
  fact_set: FACT_SET,
  citations: [CITATION],
  risk_level: "medium",
  risk_reasons: ["证据完整性待核实"],
  nli: { status: "pass", score: 0.9, reason: "词面重叠达阈值" },
  mode: "template",
  disclaimers: ["不构成法律意见"],
};

export const KG_RESULT: KgQueryResponse = {
  question: "违约责任",
  matched_node: { id: "c:breach", node_type: "concept", name: "违约责任" },
  paths: [
    {
      nodes: [
        { id: "c:breach", node_type: "concept", name: "违约责任" },
        { id: "s:CN-MINFA-577", node_type: "statute", name: "民法典 第五百七十七条" },
      ],
      relations: ["依据条文"],
    },
    {
      nodes: [
        { id: "s:CN-MINFA-577", node_type: "statute", name: "民法典 第五百七十七条" },
        { id: "s:JP-MIN-415", node_type: "statute", name: "民法 第四百十五条" },
      ],
      relations: ["ANALOGOUS_TO"],
    },
    {
      nodes: [
        { id: "c:breach", node_type: "concept", name: "违约责任" },
        { id: "e:act", node_type: "element", name: "违约行为" },
      ],
      relations: ["构成要件"],
    },
  ],
  answer: "【违约责任】知识图谱展开（3 条关系路径）：\n· 构成要件：违约行为",
  statute_ids: ["CN-MINFA-577", "JP-MIN-415"],
  related_cases: [
    "Chwee Kin Keong v Digilandmall.com Pte Ltd [2005] SGCA 2; [2005] 1 SLR(R) 502  要旨：网上打印机标价错误，合同因单方错误（买家明知）无效。",
    "Quoine Pte Ltd v B2C2 Ltd [2020] SGCA(I) 2  要旨：确定性算法之间的交互可成立有约束力的合同。",
    "Spandeck Engineering (S) Pte Ltd v Defence Science & Technology Agency [2007] SGCA 37  要旨：过失侵权注意义务三步检验框架。",
  ],
  backend: "memory",
  disclaimer: "知识图谱为结构化概览，具体适用请核对法条原文；不构成法律意见。",
};

export const GRAPH_RESULT: ConsultGraphResponse = {
  status: "degraded",
  answer: "⚠️【引用支撑不足·已降级】结论与所引法条的蕴含关系校验未通过。",
  citations: [CITATION],
  facts: FACT_SET,
  nli: { status: "degraded", score: 0.1, reason: "词面重叠过低" },
  confidence: 0.4,
  trace: [
    "intake(ok)",
    "structure_facts(4 facts, 1 claims)",
    "retrieve(1 hits, top=0.350)",
    "generate_draft(server)",
    "nli_verify(degraded, 0.1)",
  ],
  adversarial_notes: null,
  answer_mode: "server",
  interrupted: true,
  thread_id: "consult-test123",
};

export const GRAPH_RESUMED: ConsultGraphResponse = {
  ...GRAPH_RESULT,
  status: "degraded",
  interrupted: false,
  trace: [...GRAPH_RESULT.trace, "human_confirm(approve)", "finalize(degraded, conf=0.4)"],
};
