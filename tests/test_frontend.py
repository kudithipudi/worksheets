"""Frontend page (Jinja2-rendered) tests."""

from app.constants import VALID_SUBJECTS


class TestFrontend:

    async def test_root_returns_html(self, client):
        r = await client.get("/")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]

    async def test_html_contains_alpine(self, client):
        r = await client.get("/")
        assert "alpinejs" in r.text

    async def test_html_contains_all_subjects(self, client):
        r = await client.get("/")
        for s in VALID_SUBJECTS:
            assert s in r.text

    async def test_html_contains_four_levels(self, client):
        r = await client.get("/")
        for level in ["Approaching", "On-Level", "Advanced", "GT/Enrichment"]:
            assert level in r.text, f"Level '{level}' not found in HTML"

    async def test_html_contains_teks_topics(self, client):
        r = await client.get("/")
        assert "Number and Operations" in r.text
        assert "Organisms and Environments" in r.text

    async def test_html_contains_question_bank(self, client):
        r = await client.get("/")
        assert "Question Bank" in r.text

    async def test_html_contains_noscript(self, client):
        r = await client.get("/")
        assert "<noscript>" in r.text

    async def test_html_contains_question_types(self, client):
        r = await client.get("/")
        assert "Multiple Choice" in r.text
        assert "Mixed" in r.text

    async def test_html_contains_lab_chrome(self, client):
        """Shared chrome: lab link in header and footer attribution."""
        r = await client.get("/")
        assert "lab.kudithipudi.org" in r.text
        assert "Kudithipudi AI Lab" in r.text

    async def test_print_css_preserved(self, client):
        """Built stylesheet keeps the print-ready worksheet rules."""
        r = await client.get("/static/css/app.css")
        assert r.status_code == 200
        assert "@media print" in r.text
        assert "page-break-inside" in r.text
