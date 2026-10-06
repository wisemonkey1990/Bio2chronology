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
        self.assertEqual((t.year, t.confidence), (1920, "inferred"))
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
