"""Proofreader runs against a fake Claude client: no API key, no network."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest import mock

import anthropic
try:
    import httpx2 as httpx  # anthropic 2.x is built on httpx2
except ImportError:
    import httpx

from ocrkit import proofread as pr, records as rec

OCR = "The Kotzker said that truth cannot be imitated.12 He repeated it in 1847 and later. " * 4
GOOD = ("The Kotzker said that truth cannot be imitated.^12^ He repeated it in 1847 and later. " * 4
        ).rstrip() + "\n--- notes ---\n12. See Emet ve-Emunah.\np. 57"


def msg(text, stop="end_turn"):
    return NS(content=[NS(type="text", text=text)], stop_reason=stop,
              usage=NS(input_tokens=1000, output_tokens=500))


def rate_limit():
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return anthropic.RateLimitError("slow down", body=None,
                                    response=httpx.Response(429, headers={"retry-after": "0"}, request=req))


class FakeClient:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []
        self.messages = NS(create=self._create, batches=None)

    def _create(self, **kw):
        self.calls.append(kw)
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def make_dir(n_pages=3):
    d = Path(tempfile.mkdtemp())
    for n in range(1, n_pages + 1):
        rec.append_record(d / "ocr.jsonl", {"page": n, "scan": n, "lang": "eng", "script": None,
                                            "image": None, "low_conf": ["Kotzlcer"], "text": OCR})
    return d


@mock.patch("time.sleep", lambda s: None)
class Sequential(unittest.TestCase):
    def test_all_good_and_outputs(self):
        d = make_dir(2)
        c = FakeClient([msg(GOOD), msg(GOOD)])
        pr.run(d, client=c)
        proof = rec.latest_by_page(rec.load_records(d / "proof.jsonl"))
        self.assertEqual([proof[n]["status"] for n in (1, 2)], ["ok", "ok"])
        self.assertEqual(proof[1]["printed_page"], "57")
        self.assertGreater(proof[1]["change_rate"], 0)
        self.assertIn("Kotzlcer", c.calls[0]["messages"][0]["content"])   # low-confidence words sent
        self.assertEqual(c.calls[0]["extra_body"], {"output_config": {"effort": "low"}})
        self.assertIn("PAGE 1  (p. 57)", (d / "proof.txt").read_text())
        self.assertTrue((d / "proof-report.md").exists())

    def test_retry_with_feedback_then_ok(self):
        d = make_dir(1)
        c = FakeClient([msg(GOOD.replace("^12^", "[12]")), msg(GOOD)])
        pr.run(d, client=c)
        r = rec.latest_by_page(rec.load_records(d / "proof.jsonl"))[1]
        self.assertEqual((r["status"], r["attempts"]), ("ok", 2))
        self.assertIn("write them as ^n^", c.calls[1]["messages"][0]["content"])

    def test_kept_ocr_after_three_failures(self):
        d = make_dir(1)
        pr.run(d, client=FakeClient([msg("I cannot do that.")] * 3))
        r = rec.latest_by_page(rec.load_records(d / "proof.jsonl"))[1]
        self.assertEqual(r["status"], "kept_ocr")
        self.assertEqual(r["text"], OCR)
        self.assertIn("OCR text kept", (d / "proof-report.md").read_text())

    def test_rate_limits_do_not_use_up_attempts(self):
        d = make_dir(1)
        pr.run(d, client=FakeClient([rate_limit(), rate_limit(), rate_limit(), msg(GOOD)]))
        r = rec.latest_by_page(rec.load_records(d / "proof.jsonl"))[1]
        self.assertEqual((r["status"], r["attempts"]), ("ok", 1))

    def test_resume_and_repair(self):
        d = make_dir(3)
        pr.run(d, client=FakeClient([msg(GOOD), msg("I cannot")] + [msg("I cannot")] * 2 + [msg(GOOD)]))
        proof = rec.latest_by_page(rec.load_records(d / "proof.jsonl"))
        self.assertEqual([proof[n]["status"] for n in (1, 2, 3)], ["ok", "kept_ocr", "ok"])
        c = FakeClient([])
        pr.run(d, client=c)                       # plain re-run: nothing left
        self.assertEqual(c.calls, [])
        c = FakeClient([msg(GOOD)])
        pr.run(d, client=c, repair=True)          # only page 2
        self.assertEqual(len(c.calls), 1)
        proof = rec.latest_by_page(rec.load_records(d / "proof.jsonl"))
        self.assertEqual(proof[2]["status"], "ok")
        self.assertEqual(len(rec.load_records(d / "proof.jsonl")), 3)   # compacted

    def test_fatal_error_stops_and_keeps_done_pages(self):
        d = make_dir(3)
        req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        billing = anthropic.APIStatusError("Your credit balance is too low", body=None,
                                           response=httpx.Response(400, request=req))
        with self.assertRaises(SystemExit):
            pr.run(d, client=FakeClient([msg(GOOD), billing]))
        proof = rec.latest_by_page(rec.load_records(d / "proof.jsonl"))
        self.assertEqual(list(proof), [1])

    def test_vision_sends_image(self):
        from PIL import Image
        d = make_dir(1)
        (d / "pages").mkdir()
        Image.new("RGB", (50, 70), "white").save(d / "pages" / "page_0001.tif")
        recs = rec.load_records(d / "ocr.jsonl")
        recs[0]["image"] = "pages/page_0001.tif"
        rec.write_records_atomic(d / "ocr.jsonl", recs)
        c = FakeClient([msg(GOOD)])
        pr.run(d, client=c)
        content = c.calls[0]["messages"][0]["content"]
        self.assertEqual(content[0]["source"]["media_type"], "image/png")   # tif converted
        self.assertIn("image of the printed page", c.calls[0]["system"])
        self.assertEqual(rec.latest_by_page(rec.load_records(d / "proof.jsonl"))[1]["mode"], "vision")


class FakeBatches:
    def __init__(self, outcomes):
        self.outcomes = outcomes   # {page: message or "errored"}
        self.created = None
        self.polls = 0

    def create(self, requests):
        self.created = requests
        return NS(id="msgbatch_test")

    def retrieve(self, batch_id):
        self.polls += 1
        status = "ended" if self.polls > 1 else "in_progress"
        return NS(processing_status=status, request_counts=NS(succeeded=0, processing=1))

    def results(self, batch_id):
        for r in self.created:
            n = int(r["custom_id"].split("-")[1])
            o = self.outcomes[n]
            if o == "errored":
                yield NS(custom_id=r["custom_id"], result=NS(type="errored"))
            else:
                yield NS(custom_id=r["custom_id"], result=NS(type="succeeded", message=o))


@mock.patch("time.sleep", lambda s: None)
class Batch(unittest.TestCase):
    def test_batch_with_retries(self):
        d = make_dir(3)
        c = FakeClient([msg(GOOD), msg(GOOD)])      # used for the two retries
        c.messages.batches = FakeBatches({1: msg(GOOD), 2: msg("I cannot"), 3: "errored"})
        pr.run(d, client=c, batch=True)
        req = c.messages.batches.created[0]
        self.assertEqual(req["params"]["output_config"], {"effort": "low"})
        proof = rec.latest_by_page(rec.load_records(d / "proof.jsonl"))
        self.assertEqual([proof[n]["status"] for n in (1, 2, 3)], ["ok", "ok", "ok"])
        self.assertEqual(proof[1]["usage"]["batched"], True)
        self.assertEqual(proof[2]["attempts"], 2)              # 1 in batch + 1 retry
        self.assertIn("Your previous attempt was rejected", c.calls[0]["messages"][0]["content"])   # feedback carried over
        self.assertFalse((d / "proof-batch.json").exists())


if __name__ == "__main__":
    unittest.main()
