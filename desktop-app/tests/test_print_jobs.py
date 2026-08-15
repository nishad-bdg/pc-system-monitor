import json

from system_info import print_jobs
from system_info.print_jobs import (
    PrintEvent,
    collect_macos_events,
    collect_new_print_events,
    collect_windows_events,
    _parse_iso_ts,
    _parse_win_307,
)


class FakeResponse:
    def __init__(self, ok=True):
        self._ok = ok

    def raise_for_status(self):
        if not self._ok:
            raise Exception("http error")


def _write_page_log(path, lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_parse_win_307():
    msg = (
        "Document 5, report.pdf owned by DOMAIN\\john printed on Office HP "
        "through port IP_192.168.1.10.  Size in bytes: 1234. Pages printed: 2."
    )
    parsed = _parse_win_307(msg)
    assert parsed["document"] == "report.pdf"
    assert parsed["user"] == "DOMAIN\\john"
    assert parsed["printer"] == "Office HP"
    assert parsed["pages"] == 2


def test_parse_win_307_minimal():
    parsed = _parse_win_307("Document 3, invoice.docx owned by mary printed on DeskJet.")
    assert parsed["document"] == "invoice.docx"
    assert parsed["user"] == "mary"


def test_parse_iso_ts():
    assert _parse_iso_ts("2026-08-15T10:00:00.000Z") is not None
    assert _parse_iso_ts(None) is None


def test_macos_page_log_collect_and_dedup(tmp_path):
    state_path = tmp_path / "print_jobs.json"
    print_jobs.override_state_path(state_path)

    lines = [
        'First_Floor nisha 100 1 2 5000 1750000000 1750000010 "Year Report.pdf"',
        'Second_Floor nisha 101 1 1 2000 1750000060 1750000070 "Invoice.pdf"',
    ]
    page_log = tmp_path / "page_log"
    _write_page_log(page_log, lines)

    orig_log = print_jobs._MACOS_PAGE_LOG
    print_jobs._MACOS_PAGE_LOG = str(page_log)
    try:
        # Simulate macOS collection against our temp page log.
        items, max_ts = collect_macos_events(None)
        assert len(items) == 2
        assert items[0].printer == "First_Floor"
        assert items[0].document == "Year Report.pdf"
        assert items[0].pages == 2
        assert items[1].user == "nisha"
        assert max_ts == 1750000070

        # Second run with watermark should yield nothing new.
        items2, max_ts2 = collect_macos_events(max_ts)
        assert items2 == []
        assert max_ts2 == max_ts
    finally:
        print_jobs._MACOS_PAGE_LOG = orig_log


def test_windows_events_watermark():
    payload = json.dumps(
        [
            {
                "RecordId": 10,
                "TimeCreated": "2026-08-15T10:00:00.000Z",
                "Message": "Document 1, a.pdf owned by bob printed on HP01 through port USB001. Pages printed: 4.",
            },
            {
                "RecordId": 11,
                "TimeCreated": "2026-08-15T10:05:00.000Z",
                "Message": "Document 2, b.xlsx owned by alice printed on Floor Laser through port IP_10.0.0.5. Pages printed: 9.",
            },
        ]
    )
    orig_run = print_jobs._run
    print_jobs._run = lambda cmd, timeout=25.0, cwd=None: payload
    try:
        items, newest = collect_windows_events(None)
        assert len(items) == 2
        assert items[0].document == "a.pdf"
        assert items[1].printer == "Floor Laser"
        assert newest == 11

        items2, _ = collect_windows_events(11)
        assert items2 == []
    finally:
        print_jobs._run = orig_run


def test_print_event_signature():
    a = PrintEvent(printer="HP", document="a.pdf", job_id="1")
    b = PrintEvent(printer="HP", document="a.pdf", job_id="1")
    c = PrintEvent(printer="HP", document="a.pdf", job_id="2")
    assert a.signature == b.signature
    assert a.signature != c.signature


def test_skip_empty_newline_removed():
    # Regression guard: previously the parser could emit empty printers.
    raw = "Office_HP alice 1 1 3 100 1750000000 1750000005 MyDoc.pdf"
    match = print_jobs._MACOS_LINE_RE.match(raw)
    assert match is not None
    assert match.group("title").strip() == "MyDoc.pdf"