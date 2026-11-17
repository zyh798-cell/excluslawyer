/**
 * 普通人友好层 P0：生活场景配置（配置化、可扩展）。
 *
 * 设计约定：
 * - 场景与问卷字段全部配置化，新增场景只需在此追加一条，无需改组件；
 * - 每个场景含：名称、一句话适用说明、2–4 个典型问题标签、关联法域标签、问卷字段；
 * - 图标名统一走 ScenarioIcon 的内联 SVG（不使用 emoji）；
 * - 本层只做前端采集骨架：摘要预填进现有提问框，后续复用既有 /api/ask 流程，不新增后端逻辑。
 */

export type JurisdictionCode = "CN" | "JP" | "KR" | "SG";

export type ScenarioId =
  | "rental"
  | "employment"
  | "consumer"
  | "family"
  | "accident"
  | "debt"
  | "study"
  | "other";

export type ScenarioIconName =
  | "home"
  | "briefcase"
  | "shopping-bag"
  | "heart"
  | "car"
  | "coins"
  | "graduation-cap"
  | "message-circle";

export type ScenarioFieldType = "text" | "textarea" | "number" | "select" | "date";

export interface ScenarioFieldOption {
  value: string;
  label: string;
}

export interface ScenarioField {
  key: string;
  label: string;
  type: ScenarioFieldType;
  placeholder?: string;
  options?: ScenarioFieldOption[];
  required?: boolean;
  hint?: string;
}

export interface Scenario {
  id: ScenarioId;
  name: string;
  /** 一句话适用说明 */
  summary: string;
  /** 2–4 个典型问题标签 */
  tags: string[];
  /** 关联法域标签 */
  jurisdictions: JurisdictionCode[];
  icon: ScenarioIconName;
  /** 问卷字段（按顺序分步展示） */
  fields: ScenarioField[];
  /** 生成案情摘要时的诉求提示句 */
  askPrompt: string;
}

export const JURISDICTION_LABELS: Record<JurisdictionCode, string> = {
  CN: "中国",
  JP: "日本",
  KR: "韩国",
  SG: "新加坡",
};

export const SCENARIOS: Scenario[] = [
  {
    id: "rental",
    name: "租房与押金",
    summary: "押金被扣、押金拿不回、没签合同、房东提前解约",
    tags: ["押金被扣", "押金不退", "没签合同"],
    jurisdictions: ["CN"],
    icon: "home",
    fields: [
      { key: "city", label: "城市", type: "text", placeholder: "例如：杭州", required: true },
      {
        key: "rentalType",
        label: "租房类型",
        type: "select",
        options: [
          { value: "个人房东直租", label: "个人房东直租" },
          { value: "中介", label: "中介" },
          { value: "长租公寓", label: "长租公寓" },
          { value: "短租", label: "短租" },
        ],
      },
      {
        key: "dispute",
        label: "争议事项",
        type: "select",
        options: [
          { value: "押金不退", label: "押金不退" },
          { value: "提前解约押金不退", label: "提前解约押金不退" },
          { value: "租金纠纷", label: "租金纠纷" },
          { value: "房屋维修与安全隐患", label: "房屋维修与安全隐患" },
          { value: "其他", label: "其他" },
        ],
        required: true,
      },
      {
        key: "contract",
        label: "是否签订书面合同",
        type: "select",
        options: [
          { value: "是，已签书面合同", label: "是，已签书面合同" },
          { value: "否，仅口头约定", label: "否，仅口头约定" },
          { value: "否，只有收据/转账记录", label: "否，只有收据/转账记录" },
        ],
      },
      { key: "deposit", label: "押金金额（元）", type: "number", placeholder: "例如：2000" },
      {
        key: "evidence",
        label: "沟通与付款记录",
        type: "textarea",
        placeholder: "例如：有微信聊天记录、转账凭证、房东短信催租记录……",
        hint: "写清有哪些书面材料，可直接影响举证质证结论",
      },
    ],
    askPrompt:
      "请分析押金归属依据、房东扣押金有无法律依据、我能否要求返还并主张违约责任，并标注对应法条原文。",
  },
  {
    id: "employment",
    name: "劳动与离职",
    summary: "拖欠工资、未签合同二倍工资、加班费、被违法辞退",
    tags: ["拖欠工资", "二倍工资", "违法解除"],
    jurisdictions: ["CN"],
    icon: "briefcase",
    fields: [
      { key: "hireDate", label: "入职时间", type: "text", placeholder: "例如：2024 年 3 月", required: true },
      {
        key: "contractType",
        label: "合同类型",
        type: "select",
        options: [
          { value: "已签书面劳动合同", label: "已签书面劳动合同" },
          { value: "未签书面劳动合同", label: "未签书面劳动合同" },
          { value: "口头约定", label: "口头约定" },
          { value: "劳务/承揽（非劳动关系）", label: "劳务/承揽（非劳动关系）" },
        ],
        required: true,
      },
      {
        key: "dispute",
        label: "争议事项",
        type: "select",
        options: [
          { value: "拖欠工资", label: "拖欠工资" },
          { value: "未签书面劳动合同二倍工资", label: "未签书面劳动合同二倍工资" },
          { value: "加班费/未休年假", label: "加班费/未休年假" },
          { value: "违法解除或违法裁员", label: "违法解除或违法裁员" },
          { value: "社保未缴或未足额缴纳", label: "社保未缴或未足额缴纳" },
          { value: "其他", label: "其他" },
        ],
        required: true,
      },
      {
        key: "leaveReason",
        label: "离职原因",
        type: "select",
        options: [
          { value: "主动辞职", label: "主动辞职" },
          { value: "被辞退/解除", label: "被辞退/解除" },
          { value: "协商解除", label: "协商解除" },
          { value: "合同到期终止", label: "合同到期终止" },
          { value: "仍在职（未离职）", label: "仍在职（未离职）" },
        ],
      },
      {
        key: "claim",
        label: "欠薪或补偿诉求",
        type: "textarea",
        placeholder: "例如：要求支付 2025 年 1–3 月工资 1.5 万元及经济补偿……",
      },
      {
        key: "settlement",
        label: "工资与离职证明结算情况",
        type: "select",
        options: [
          { value: "已全部结清", label: "已全部结清" },
          { value: "部分未结", label: "部分未结" },
          { value: "全部未结", label: "全部未结" },
          { value: "未出具离职证明", label: "未出具离职证明" },
        ],
      },
    ],
    askPrompt:
      "请分析我的请求权基础（是否需劳动仲裁前置）、金额与计算方式、时效风险，以及下一步应准备的证据清单，并标注对应法条原文。",
  },
  {
    id: "consumer",
    name: "消费维权",
    summary: "退款难、货不对板、预付卡跑路、价格欺诈",
    tags: ["退款", "货不对板", "预付卡"],
    jurisdictions: ["CN"],
    icon: "shopping-bag",
    fields: [
      { key: "item", label: "购买商品或服务", type: "text", placeholder: "例如：某品牌净水器", required: true },
      {
        key: "channel",
        label: "商家类型",
        type: "select",
        options: [
          { value: "电商平台", label: "电商平台" },
          { value: "实体店", label: "实体店" },
          { value: "服务商（培训/装修/保洁等）", label: "服务商（培训/装修/保洁等）" },
          { value: "预付卡/储值", label: "预付卡/储值" },
          { value: "个人卖家", label: "个人卖家" },
        ],
      },
      {
        key: "dispute",
        label: "争议类型",
        type: "select",
        options: [
          { value: "质量问题", label: "质量问题" },
          { value: "虚假宣传", label: "虚假宣传" },
          { value: "退款/退费困难", label: "退款/退费困难" },
          { value: "预付卡商家跑路", label: "预付卡商家跑路" },
          { value: "价格欺诈", label: "价格欺诈" },
          { value: "其他", label: "其他" },
        ],
        required: true,
      },
      { key: "amount", label: "涉及金额（元）", type: "number", placeholder: "例如：2999" },
      {
        key: "complained",
        label: "是否已投诉",
        type: "select",
        options: [
          { value: "未投诉", label: "未投诉" },
          { value: "已向平台投诉", label: "已向平台投诉" },
          { value: "已向 12315 投诉", label: "已向 12315 投诉" },
          { value: "已提起诉讼", label: "已提起诉讼" },
        ],
      },
      { key: "claim", label: "你的诉求", type: "textarea", placeholder: "例如：要求全额退款并赔偿延误损失……" },
    ],
    askPrompt:
      "请分析维权路径（协商/平台/行政处罚/诉讼）、对方可能的抗辩、时效与管辖要点，并标注对应法条原文。",
  },
  {
    id: "family",
    name: "婚姻家庭",
    summary: "离婚财产分割、抚养权、彩礼、共同债务",
    tags: ["离婚分割", "抚养权", "彩礼"],
    jurisdictions: ["CN"],
    icon: "heart",
    fields: [
      {
        key: "status",
        label: "婚姻状况",
        type: "select",
        options: [
          { value: "已登记结婚", label: "已登记结婚" },
          { value: "未登记（事实婚/同居）", label: "未登记（事实婚/同居）" },
          { value: "已协议离婚", label: "已协议离婚" },
          { value: "诉讼离婚中", label: "诉讼离婚中" },
          { value: "分居中", label: "分居中" },
        ],
        required: true,
      },
      {
        key: "dispute",
        label: "争议事项",
        type: "select",
        options: [
          { value: "离婚及财产分割", label: "离婚及财产分割" },
          { value: "子女抚养权", label: "子女抚养权" },
          { value: "彩礼返还", label: "彩礼返还" },
          { value: "夫妻共同债务", label: "夫妻共同债务" },
          { value: "分居期间财产", label: "分居期间财产" },
          { value: "其他", label: "其他" },
        ],
        required: true,
      },
      { key: "timeline", label: "关键时间点", type: "text", placeholder: "例如：2021 年 5 月结婚，2023 年 8 月生育" },
      {
        key: "property",
        label: "是否涉及财产",
        type: "select",
        options: [
          { value: "有（房产/存款/股权等）", label: "有（房产/存款/股权等）" },
          { value: "无财产争议", label: "无财产争议" },
          { value: "不确定", label: "不确定" },
        ],
      },
      { key: "claim", label: "你的诉求", type: "textarea", placeholder: "例如：要求分割夫妻共同财产并确定抚养权……" },
    ],
    askPrompt:
      "请分析相关制度与举证要点、可能的裁判结果区间、我应准备哪些材料，并标注对应法条原文。",
  },
  {
    id: "accident",
    name: "交通事故与人身损害",
    summary: "责任认定、赔偿范围、误工费与工伤认定",
    tags: ["责任认定", "赔偿范围", "误工费"],
    jurisdictions: ["CN"],
    icon: "car",
    fields: [
      { key: "date", label: "事故时间", type: "date", required: true },
      {
        key: "type",
        label: "事故类型",
        type: "select",
        options: [
          { value: "车辆之间碰撞", label: "车辆之间碰撞" },
          { value: "行人被撞", label: "行人被撞" },
          { value: "工伤事故（单位内）", label: "工伤事故（单位内）" },
          { value: "其他", label: "其他" },
        ],
        required: true,
      },
      {
        key: "liability",
        label: "责任认定",
        type: "select",
        options: [
          { value: "已认定，对方全责", label: "已认定，对方全责" },
          { value: "已认定，对方部分责任", label: "已认定，对方部分责任" },
          { value: "已认定，我方全责", label: "已认定，我方全责" },
          { value: "未出具事故认定书", label: "未出具事故认定书" },
        ],
      },
      { key: "injury", label: "伤情与治疗情况", type: "textarea", placeholder: "例如：左腕骨折，住院 12 天，误工 3 个月……" },
      { key: "claim", label: "赔偿诉求", type: "textarea", placeholder: "例如：要求赔偿医疗费、误工费、护理费等共计……" },
      {
        key: "insurance",
        label: "保险与理赔情况",
        type: "select",
        options: [
          { value: "已投保且已理赔", label: "已投保且已理赔" },
          { value: "已投保未理赔", label: "已投保未理赔" },
          { value: "未投保", label: "未投保" },
          { value: "对方未投保/保险不足", label: "对方未投保/保险不足" },
        ],
      },
    ],
    askPrompt:
      "请分析责任认定与赔偿范围（医疗费/误工费等）的法律依据、举证要点与时效，并标注对应法条原文。",
  },
  {
    id: "debt",
    name: "小额借贷与合同纠纷",
    summary: "欠款不还、借条缺失、对方失联、催收无果",
    tags: ["欠款不还", "借条", "催收"],
    jurisdictions: ["CN"],
    icon: "coins",
    fields: [
      {
        key: "relation",
        label: "关系类型",
        type: "select",
        options: [
          { value: "民间借贷", label: "民间借贷" },
          { value: "买卖合同", label: "买卖合同" },
          { value: "服务/承揽合同", label: "服务/承揽合同" },
          { value: "保证/担保", label: "保证/担保" },
          { value: "其他", label: "其他" },
        ],
        required: true,
      },
      { key: "amount", label: "争议金额（元）", type: "number", placeholder: "例如：50000", required: true },
      {
        key: "evidence",
        label: "书面证据",
        type: "select",
        options: [
          { value: "有借条/合同", label: "有借条/合同" },
          { value: "只有转账记录", label: "只有转账记录" },
          { value: "只有聊天记录", label: "只有聊天记录" },
          { value: "无书面证据", label: "无书面证据" },
        ],
        required: true,
      },
      { key: "dueDate", label: "约定还款时间", type: "text", placeholder: "例如：2025 年 6 月 30 日" },
      {
        key: "attitude",
        label: "对方态度",
        type: "select",
        options: [
          { value: "承认欠款", label: "承认欠款" },
          { value: "部分承认", label: "部分承认" },
          { value: "否认", label: "否认" },
          { value: "失联/拒接", label: "失联/拒接" },
        ],
      },
      { key: "claim", label: "你的诉求", type: "textarea", placeholder: "例如：要求返还本金及约定利息……" },
    ],
    askPrompt:
      "请分析请求权基础与证据是否充分、诉讼时效、管辖与保全建议，并标注对应法条原文。",
  },
  {
    id: "study",
    name: "留学签证与学业事务",
    summary: "签证被拒、居留续签、学费纠纷、学历认证",
    tags: ["签证被拒", "居留续签", "学费纠纷"],
    jurisdictions: ["CN", "JP", "KR", "SG"],
    icon: "graduation-cap",
    fields: [
      {
        key: "matter",
        label: "事项类型",
        type: "select",
        options: [
          { value: "签证申请/被拒", label: "签证申请/被拒" },
          { value: "居留资格续签", label: "居留资格续签" },
          { value: "学费与住宿费纠纷", label: "学费与住宿费纠纷" },
          { value: "学历学位认证", label: "学历学位认证" },
          { value: "开除学籍/退学", label: "开除学籍/退学" },
          { value: "其他", label: "其他" },
        ],
        required: true,
      },
      { key: "school", label: "学校与专业", type: "text", placeholder: "例如：某大学 研究生（计算机）" },
      {
        key: "status",
        label: "当前身份",
        type: "select",
        options: [
          { value: "学生签证在境内", label: "学生签证在境内" },
          { value: "工作签证在境内", label: "工作签证在境内" },
          { value: "人在境外（准备申请）", label: "人在境外（准备申请）" },
          { value: "其他", label: "其他" },
        ],
      },
      { key: "deadline", label: "关键时间节点", type: "text", placeholder: "例如：签证 2025 年 8 月 1 日到期" },
      { key: "detail", label: "具体问题", type: "textarea", placeholder: "例如：收到拒签信，理由为材料不足……" },
    ],
    askPrompt:
      "请分析所涉法域的规则要点、可申诉/救济路径与时间限制、应准备的材料，并标注对应法条或官方规则出处。",
  },
  {
    id: "other",
    name: "其他 / 直接提问",
    summary: "不属于以上场景，或你想直接描述问题",
    tags: ["其他问题", "直接提问"],
    jurisdictions: ["CN", "JP", "KR", "SG"],
    icon: "message-circle",
    fields: [
      {
        key: "detail",
        label: "你想咨询的问题",
        type: "textarea",
        placeholder: "用一两句话说明发生了什么、对方做了什么、你想要什么结果……",
        required: true,
      },
    ],
    askPrompt:
      "请依据现行有效法条分析我的权利、对方可能的抗辩与可行主张，并标注对应法条原文。",
  },
];

export function getScenario(id: ScenarioId): Scenario | undefined {
  return SCENARIOS.find((s) => s.id === id);
}

/**
 * 把问卷填写值整理为结构化案情摘要（预填进提问框，用户可再编辑）。
 * 未填写的可选字段自动跳过，不产生空值噪声。
 */
export function buildScenarioSummary(
  scenario: Scenario,
  values: Record<string, string>
): string {
  const facts = scenario.fields
    .map((f) => ({ label: f.label, value: (values[f.key] ?? "").trim() }))
    .filter((x) => x.value.length > 0)
    .map((x) => `${x.label}：${x.value}`)
    .join("；");
  const head = `【${scenario.name}】`;
  return facts
    ? `${head}${facts}。${scenario.askPrompt}`
    : `${head}${scenario.askPrompt}`;
}
