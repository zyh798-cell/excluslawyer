# -*- coding: utf-8 -*-
"""数据管道单元测试（离线：不访问网络）。"""
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.data_pipeline.base import RawArticle, RawLaw  # noqa: E402
from app.data_pipeline.cn_flk import cn_num_to_int, split_cn_articles  # noqa: E402
from app.data_pipeline.jp_egov import JpEgovSource  # noqa: E402
from app.data_pipeline.kr_law import KrLawSource  # noqa: E402
from app.data_pipeline.normalizer import article_key, normalize, slug_tag, validate  # noqa: E402
from app.data_pipeline.sg_sso import SgSsoSource, split_pdf_text  # noqa: E402


class TestCnParse:
    def test_cn_num(self):
        assert cn_num_to_int("五") == 5
        assert cn_num_to_int("十") == 10
        assert cn_num_to_int("十八") == 18
        assert cn_num_to_int("五百八十四") == 584
        assert cn_num_to_int("一千二百六十") == 1260

    def test_split_basic(self):
        text = "第一条　为了保护民事主体。第二条　民法调整平等主体之间的人身关系和财产关系。第三条　民事主体的人身权利。"
        arts = split_cn_articles(text)
        assert [a.article_no for a in arts] == ["第一条", "第二条", "第三条"]
        assert "保护民事主体" in arts[0].text

    def test_split_caption(self):
        arts = split_cn_articles("第一条（目的）　为规范活动。第二条　定义如下。")
        assert arts[0].caption == "目的"
        assert arts[0].text.startswith("为规范")

    def test_split_ignores_body_mention(self):
        text = "第一条　依照第三条的规定处理。第二条　本法自施行。"
        arts = split_cn_articles(text)
        assert len(arts) == 2
        assert "第三条" in arts[0].text  # 正文提及不切分

    def test_skip_empty_body(self):
        arts = split_cn_articles("第一条　有内容。第二条")
        assert len(arts) == 1


JP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<DataRoot><Result><Code>0</Code></Result><ApplData>
<LawId>321CONSTITUTION</LawId><LawNum>Constitution</LawNum>
<LawFullText><Law Era="Showa" Year="21" LawType="Constitution" Lang="ja">
<LawBody><MainProvision>
<Article><ArticleTitle>第一条</ArticleTitle><ArticleCaption>（天皇の地位）</ArticleCaption>
<Paragraph><ParagraphNum/><ParagraphSentence><Sentence>天皇は、日本国の象徴であり日本国民統合の象徴であつて、この地位は、主権の存する日本国民の総意に基く。</Sentence></ParagraphSentence></Paragraph>
</Article>
<Article><ArticleTitle>第二条</ArticleTitle>
<Paragraph><ParagraphSentence><Sentence>皇位は、皇室典範の定めるところにより、これを世襲する。</Sentence></ParagraphSentence></Paragraph>
</Article>
</MainProvision>
<SupplProvision>
<Article><ArticleTitle>第一条</ArticleTitle>
<Paragraph><ParagraphSentence><Sentence>この法律は、公布の日から施行する。</Sentence></ParagraphSentence></Paragraph>
</Article>
</SupplProvision></LawBody></Law></LawFullText></ApplData></DataRoot>""".encode("utf-8")


class TestJpParse:
    def test_parse_law_xml(self):
        arts, meta = JpEgovSource.parse_law_xml(JP_XML)
        assert len(arts) == 3
        assert arts[0].article_no == "第一条"
        assert arts[0].caption == "天皇の地位"
        assert "象徴" in arts[0].text
        assert meta["law_num"] == "Constitution"
        # 附則条文独立命名空间
        assert arts[2].article_no == "附則第一条"
        assert article_key(arts[2].article_no) == "F1"
        assert article_key(arts[0].article_no) == "1"


KR_HTML = """<div class="lawcon"><p class="pty1_p4">
<input name="joNoList" id="Y000100" type="checkbox" value="1" />
<span class="bl"><label for="Y000100"> 제1조(법원) </label> </span> 민사에 관하여 법률에 규정이 없으면 관습법에 의한다. </p></div>
<div class="lawcon"><p class="pty1_p4">
<span class="bl"><label for="Y000200"> 제2조(신의성실) </label></span> ①권리의 행사는 신의에 좇아야 한다. </p></div>"""


class TestKrParse:
    def test_parse_body(self):
        arts = KrLawSource.parse_body(KR_HTML)
        assert len(arts) == 2
        assert arts[0].article_no == "제1조(법원)"
        assert arts[0].caption == "법원"
        assert "관습법" in arts[0].text
        assert "신의" in arts[1].text


SG_HTML = """<div class="prov1"><div class="prov1Hdr"><span class="noBold">Short title</span></div>
<div class="prov1Txt">1.&#xA0;&#xA0;This Act is the Currency Act 1967.</div></div>
<div class="prov1"><div class="prov1Hdr"><span class="noBold">Interpretation</span></div>
<div class="prov1Txt">2.&#xA0;&#xA0;(1) In this Act, unless the context otherwise requires &#x2014; "Authority" means the Monetary Authority of Singapore.</div></div>"""


class TestSgParse:
    def test_parse_provisions(self):
        arts = SgSsoSource.parse_provisions(SG_HTML)
        assert len(arts) == 2
        assert arts[0].article_no == "1."
        assert "Currency Act 1967" in arts[0].text
        assert arts[0].caption == "Short title"
        assert arts[1].article_no == "2."
        assert "Monetary Authority" in arts[1].text

    def test_parse_timeline(self):
        page = 'href="/Act/CA1967/Historical/19910201?DocDate=19910125&amp;ValidDate=19910201"'
        tl = SgSsoSource.parse_timeline(page)
        assert tl and tl[0].startswith("1991-02-01")


# 模拟 SSO PDF layout 文本：目录区（宽间距）+ 正文区（破折号式/空格式混排 +
# 行内 Rule 编号 + 空置条）+ Schedule + 修订对照表 + 立法沿革
SG_PDF_TEXT = """Informal Consolidation – version in force from 1/4/2022
ARRANGEMENT OF SECTIONS
    1.       Contracts to which Act applies
    2.       Contract of sale
    3.       Goods which have perished
    4.       Sale by auction
 1.—(1)  This Act applies to contracts of sale of goods made on or after 1 January 1894.
 (2)  In relation to contracts made on certain dates, this Act applies subject to modification.
 2.—(1)  A contract of sale of goods is a contract by which the seller transfers property.
 3.  Where there is a contract for the sale of specific goods, and the goods have perished at the time when the contract is made, the contract is void.
Rules about delivery
 4.  Where there is a contract for the sale of goods, the following rules apply.
        (a)  Rule 1.—Where there is an unconditional contract for the sale.
        (b)  Rule 2.—Where there is a contract for the sale of specific goods.
 5.  [Not applicable]
THE SCHEDULE
Sections 1(2) and (3)
 1.—(1)  This Schedule modifies this Act as it applies to contracts of sale.
 2.  In relation to a contract made on or after 18 May 1973, substitute the following.
COMPARATIVE TABLE
5.—(1)   Where the proper law of a contract for the sale of goods would be Singapore.
LEGISLATIVE HISTORY
1. Act 25 of 2021 — Courts Reform Act 2021
"""


class TestSgPdfSplit:
    def test_split_pdf_text(self):
        arts = split_pdf_text(SG_PDF_TEXT)
        assert [a.article_no for a in arts] == ["1.", "2.", "3.", "4.", "5."]
        assert "1 January 1894" in arts[0].text
        assert "Contracts to which Act applies" not in arts[0].text  # 目录条目不混入
        assert "transfers property" in arts[1].text
        assert "perished" in arts[2].text
        assert "Rule 1.—" in arts[3].text  # 行内 Rule 编号并入所属条
        assert "Rule 2.—" in arts[3].text
        assert "[Not applicable]" in arts[4].text
        joined = " ".join(a.text for a in arts)
        assert "Schedule modifies" not in joined  # Schedule 段不混入
        assert "proper law" not in joined  # 修订对照表不混入
        assert "Courts Reform" not in joined  # 立法沿革不混入

    def test_split_empty(self):
        assert split_pdf_text("") == []
        assert split_pdf_text("no numbered provisions here") == []


class TestNormalizer:
    def _raw(self):
        return RawLaw(
            source="cn_flk", source_id="bb", title="中华人民共和国民法典",
            jurisdiction="CN", language="zh",
            promulgation_date="2020-05-28", effective_date="2021-01-01",
            status="effective", amended_history=["2020-05-28 公布"],
            source_url="https://flk.npc.gov.cn/detail?id=bb",
            articles=[
                RawArticle("第一百八十八条", "诉讼时效期间为三年。"),
                RawArticle("第五百八十四条", "损失赔偿额应当相当于因违约所造成的损失。"),
            ],
        )

    def test_article_key(self):
        assert article_key("第一百八十八条") == "188"
        assert article_key("第1条") == "1"
        assert article_key("제1조의2") == "1-2"
        assert article_key("1.") == "1"
        assert article_key("第百条の二") == "100-2"
        assert article_key("第一百三十三条之一") == "133-1"
        assert article_key("第七百九条") == "709"

    def test_slug_tag_compat(self):
        assert slug_tag("中华人民共和国民法典") == "MINFA"
        assert slug_tag("中华人民共和国劳动合同法") == "LDF"

    def test_normalize_ids_match_seed_convention(self):
        stats = normalize(self._raw())
        assert [s.id for s in stats] == ["CN-MINFA-188", "CN-MINFA-584"]
        assert stats[0].status == "effective"
        assert stats[0].effective_date == "2021-01-01"
        assert stats[0].law_title == "中华人民共和国民法典"
        assert stats[0].source_url.startswith("https://flk")

    def test_validate(self):
        stats = normalize(self._raw())
        q = validate(stats)
        assert q["total"] == 2
        assert not q["duplicate_ids"]
        assert not q["too_short"]
        assert q["laws"]["中华人民共和国民法典"] == 2


class TestStatusMapping:
    def test_sxx_map(self):
        from app.data_pipeline.cn_flk import SXX_MAP
        assert SXX_MAP == {"1": "repealed", "2": "amended", "3": "effective"}
