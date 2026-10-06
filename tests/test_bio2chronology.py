import json
import unittest

from bio2chronology.export import to_csv, to_html, to_json, to_markdown
from bio2chronology.extract import LLMExtractor
from bio2chronology.models import Chronology
from bio2chronology.pipeline import build_chronology, detect_birth_year
from bio2chronology.timeexpr import TimeResolver, cn_to_int, scan


class TimeTests(unittest.TestCase):
    def test_numerals(self):
        self.assertEqual(cn_to_int("一九一八"), 1918)
        self.assertEqual(cn_to_int("十二"), 12)
        self.assertEqual(cn_to_int("二十三"), 23)

    def test_absolute_and_relative(self):
        r = TimeResolver(birth_year=1890)
        self.assertEqual(r.resolve("1918年秋，考入某校").year, 1918)
        t = r.resolve("同年冬")
        self.assertEqual((t.year, t.season, t.confidence), (1918, "冬", "relative"))
        self.assertEqual(r.resolve("次年").year, 1919)
        self.assertEqual(r.resolve("三年后").year, 1922)
        self.assertEqual(r.resolve("民国十二年三月").year, 1923)
        self.assertEqual(r.current_year, 1923)

    def test_age_idiom(self):
        t = TimeResolver(1890).resolve("而立之年")
        self.assertEqual((t.year, t.confidence), (1920, "approx"))
        self.assertEqual(TimeResolver().resolve("而立之年").year, None)

    def test_season_only_inherits_year(self):
        r = TimeResolver()
        r.resolve("1923年")
        t = r.resolve("暮春，他离开了")
        self.assertEqual((t.year, t.season, t.confidence), (1923, "暮春", "inferred"))

    def test_season_false_positives(self):
        self.assertEqual(scan("夏衍来访"), [])
        self.assertEqual(scan("秋瑾就义"), [])
        self.assertEqual(scan("他在春风中"), [])

    def test_flashback_does_not_move_cursor(self):
        r = TimeResolver()
        r.resolve("1930年")
        self.assertEqual(r.resolve("三年前").year, 1927)
        self.assertEqual(r.current_year, 1930)

    def test_unresolved_without_context(self):
        self.assertEqual(TimeResolver().resolve("次年").confidence, "unresolved")


BIO = """第一章 少年
沈某生于1895年，出生于绍兴。1908年入学，1912年毕业。同年秋，发表《初作》。
次年，赴上海求学，结识陈某。
"""


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.chron = build_chronology(BIO, "沈某")

    def test_birth_detection(self):
        self.assertEqual(detect_birth_year(BIO), 1895)

    def test_split_and_order(self):
        years = [e.year for e in self.chron.events]
        self.assertEqual(years, sorted(years))
        self.assertEqual(years, [1895, 1908, 1912, 1912, 1913])

    def test_tags_and_sources(self):
        works = [w for e in self.chron.events for w in e.works]
        self.assertIn("初作", works)
        last = self.chron.events[-1]
        self.assertEqual(last.places, ["上海"])
        self.assertEqual(last.people, ["陈某"])
        self.assertTrue(last.sources[0].quote.startswith("次年"))

    def test_dedupe_merges_sources(self):
        text = "第一章\n1908年，他考入某校。\n第二章\n1908年，他考入某校。\n"
        c = build_chronology(text)
        self.assertEqual(len(c.events), 1)
        self.assertEqual(len(c.events[0].sources), 2)


class ExportTests(unittest.TestCase):
    def test_rejected_hidden_and_roundtrip(self):
        c = build_chronology(BIO, "沈某")
        c.events[0].status = "rejected"
        c2 = Chronology.from_dict(json.loads(to_json(c)))
        self.assertEqual(len(c2.events), len(c.events))
        self.assertNotIn("生于1895年", to_markdown(c2))
        self.assertEqual(to_csv(c2).count("\n"), len(c.events))  # header + live rows
        self.assertIn("沈某年谱", to_html(c2))

    def test_html_escapes_script_end(self):
        c = build_chronology("1900年，他写下</script>。", "x")
        self.assertNotIn("</script>。", to_html(c).split('id="data"')[1].split("</script>")[0])


class LLMTests(unittest.TestCase):
    def test_llm_extractor_with_fake_client(self):
        reply = '```json\n[{"time_expr":"1918年","summary":"离家","quote":"1918年，他离家。","paragraph":1},' \
                '{"time_expr":"同年秋","summary":"考入某校","quote":"同年秋，他考入某校。",' \
                '"category":"教育","people":[],"places":[],"works":[],"paragraph":1}]\n```'
        c = build_chronology("第一章\n1918年，他离家。同年秋，他考入某校。\n", "x",
                             extractor=LLMExtractor(complete=lambda p: reply))
        self.assertEqual((c.events[1].year, c.events[1].season, c.events[1].category), (1918, "秋", "教育"))


if __name__ == "__main__":
    unittest.main()


class SiteTests(unittest.TestCase):
    def test_build_site(self):
        import tempfile
        from pathlib import Path
        from bio2chronology.site import build_site
        with tempfile.TemporaryDirectory() as t:
            people, out = Path(t, "people"), Path(t, "site")
            d = people / "x"
            d.mkdir(parents=True)
            c = build_chronology(BIO, "沈某")
            c.events[0].status = "rejected"
            (d / "chronology.json").write_text(to_json(c), encoding="utf-8")
            (d / "meta.json").write_text('{"name":"沈某","summary":"s"}', encoding="utf-8")
            self.assertEqual(build_site(people, out), 1)
            idx = json.loads((out / "data" / "index.json").read_text(encoding="utf-8"))
            self.assertEqual(idx["people"][0]["count"], len(c.events) - 1)
            self.assertTrue((out / "index.html").exists() and (out / "app.js").exists())

    def test_people_heuristic_strips_titles(self):
        from bio2chronology.classify import find_people
        self.assertEqual(find_people("结识了同窗林远山", ["林远山"]), ["林远山"])


class PilotFixTests(unittest.TestCase):
    """Behaviour found necessary in the Lu Xun pilot (people/lu-xun)."""

    def test_traditional_characters(self):
        r = TimeResolver(1881, "虚岁")
        self.assertEqual(r.resolve("其時我是十八歲").year, 1898)
        r.resolve("1909年")
        self.assertEqual(r.resolve("三年後").year, 1912)

    def test_reign_eras(self):
        self.assertEqual(TimeResolver().resolve("清光緒七年八月初三").year, 1881)
        self.assertEqual(TimeResolver().resolve("光绪19年").year, 1893)
        self.assertEqual(TimeResolver().resolve("宣统元年").year, 1909)

    def test_ordinal_years_count_from_anchor(self):
        r = TimeResolver()
        r.resolve("1909年回国")
        self.assertEqual(r.resolve("第二年就走出").year, 1910)
        self.assertEqual(r.resolve("第三年又走出").year, 1911)

    def test_parenthesised_years_ignored(self):
        self.assertIsNone(TimeResolver().resolve("仙台医学专门学校（1912年改制东北大学医学部）"))
        self.assertEqual(TimeResolver().resolve("1893年（光绪19年），下狱").year, 1893)

    def test_explicit_year_beats_age(self):
        r = TimeResolver(1881, subject_names=["鲁迅", "周树人"])
        self.assertEqual(r.resolve("1918年，36岁的周树人首次用笔名").year, 1918)

    def test_other_peoples_age_ignored(self):
        r = TimeResolver(1881, subject_names=["鲁迅"])
        self.assertIsNone(r.resolve("与时年28岁的朱安结婚"))
        self.assertEqual(r.resolve("45岁的鲁迅离开厦门").year, 1926)

    def test_age_reckoning(self):
        self.assertEqual(TimeResolver(1881, "虚岁").resolve("十三歲時").year, 1893)
        self.assertEqual(TimeResolver(1881, "周岁").resolve("十三岁时").year, 1894)
        r = TimeResolver(1881, "周岁", birth_month=9)
        self.assertEqual(r.resolve("三月，二十岁").year, 1902)  # before the birthday → next year

    def test_no_inheriting_years_before_birth(self):
        c = build_chronology("祖父于1871年中进士。传主童年就读私塾。\n他生于1881年。", "x", 1881)
        self.assertIsNone(next(e for e in c.events if "私塾" in e.summary).year)

    def test_time_only_clause_joins_next(self):
        c = build_chronology("1918年，36岁的他发表小说。", "他", 1881)
        self.assertEqual([e.year for e in c.events], [1918])


class ReviewOverlayTests(unittest.TestCase):
    def test_overlay_survives_reconversion_and_merges(self):
        import tempfile
        from pathlib import Path
        from bio2chronology.project import convert_person, review_event
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            (d / "source").mkdir()
            (d / "source" / "a.txt").write_text("1908年，他考入某校。1909年，他去了北京。", encoding="utf-8")
            (d / "source" / "b.txt").write_text("1908年秋，传主入学某校读书。", encoding="utf-8")
            (d / "meta.json").write_text(json.dumps({"name": "他", "sources": [
                {"file": "source/a.txt", "label": "甲"}, {"file": "source/b.txt", "label": "乙"}]}), encoding="utf-8")
            chron, _, _ = convert_person(d)
            ids = {e.summary: e.id for e in chron.events}
            target_key = next(e.key for e in chron.events if e.summary.startswith("1908年，"))
            review_event(d / "chronology.json", ids["1909年，他去了北京"], {"status": "rejected", "note": "x"})
            review_event(d / "chronology.json", ids["1908年秋，传主入学某校读书"], {"merge_into": target_key})
            chron, applied, orphaned = convert_person(d)  # regenerate from scratch
            self.assertEqual((applied, orphaned), (2, 0))
            live = [e for e in chron.events if e.status != "rejected"]
            self.assertEqual(len(live), 1)
            self.assertEqual(len(live[0].sources), 2)


class SourceTests(unittest.TestCase):
    def test_wikitext_to_text(self):
        from bio2chronology.sources import wikitext_to_text
        w = ("{{Infobox|a={{b}}}}\n== 生平 ==\n'''鲁迅'''生于[[绍兴|绍兴府]]<ref>x</ref>。-{zh-hans:简;zh-hant:繁}-\n"
             "{| class=wikitable\n|a\n|}\n== 评价 ==\n略\n")
        self.assertEqual(wikitext_to_text(w, sections=("生平",)), "# 生平\n鲁迅生于绍兴府。简\n")

    def test_evaluate(self):
        from bio2chronology.evaluate import evaluate
        c = build_chronology("1898年，考入水師學堂。1902年，赴日本。", "x")
        r = evaluate(c, {"items": [{"years": [1898], "desc": "a", "any": ["水师学堂"]},
                                   {"years": [1903], "desc": "b", "any": ["赴日本"]},
                                   {"years": [1910], "desc": "c", "any": ["不存在"]}]})
        self.assertEqual([x["status"] for x in r["items"]], ["correct", "wrong_year", "missed"])
