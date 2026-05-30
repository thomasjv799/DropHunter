# tests/test_watches.py
from pathlib import Path
from unittest.mock import MagicMock, patch

FIXTURE = Path(__file__).parent / "fixtures" / "swisstimehouse_casio_g1714.html"


def _mock_scraper_returning(html: str):
    """Build a fake cloudscraper whose .get(...) returns a response with .text=html."""
    response = MagicMock()
    response.text = html
    response.status_code = 200
    response.raise_for_status.return_value = None
    scraper = MagicMock()
    scraper.get.return_value = response
    return scraper


def test_fetch_swisstimehouse_parses_jsonld():
    from utils.watches import fetch_swisstimehouse

    html = FIXTURE.read_text()
    mock_scraper = _mock_scraper_returning(html)
    with patch("utils.watches.cloudscraper.create_scraper", return_value=mock_scraper):
        result = fetch_swisstimehouse("https://www.swisstimehouse.com/casio-g1714")

    assert result is not None
    assert result["brand"] == "Casio"
    assert result["reference"] == "G1714"
    assert "Casio" in result["name"]
    assert result["price"] == 34997.0
    assert isinstance(result["price"], float)


def test_fetch_swisstimehouse_rejects_non_swisstimehouse_url():
    from utils.watches import fetch_swisstimehouse

    result = fetch_swisstimehouse("https://www.amazon.in/some-watch")
    assert result is None


def test_fetch_swisstimehouse_returns_none_when_no_product_jsonld():
    from utils.watches import fetch_swisstimehouse

    html = "<html><head><title>nope</title></head><body>no structured data</body></html>"
    mock_scraper = _mock_scraper_returning(html)
    with patch("utils.watches.cloudscraper.create_scraper", return_value=mock_scraper):
        result = fetch_swisstimehouse("https://www.swisstimehouse.com/casio-g1714")
    assert result is None


def test_fetch_swisstimehouse_returns_none_on_request_error():
    from utils.watches import fetch_swisstimehouse

    scraper = MagicMock()
    scraper.get.side_effect = Exception("Cloudflare blocked")
    with patch("utils.watches.cloudscraper.create_scraper", return_value=scraper):
        result = fetch_swisstimehouse("https://www.swisstimehouse.com/casio-g1714")
    assert result is None


def test_fetch_swisstimehouse_handles_string_brand_and_skips_empty_price():
    from utils.watches import fetch_swisstimehouse

    # First Product has an empty-string price (must be skipped); second is valid
    # with a bare-string brand and a list-form @type.
    html = '''
    <html><head>
    <script type="application/ld+json">
    {"@type": "Product", "name": "Bad", "sku": "X", "offers": {"price": ""}}
    </script>
    <script type="application/ld+json">
    {"@type": ["Product", "Thing"], "name": "Casio Good", "sku": "G999",
     "brand": "Casio", "offers": {"price": "12345", "priceCurrency": "INR"}}
    </script>
    </head><body></body></html>
    '''
    mock_scraper = _mock_scraper_returning(html)
    with patch("utils.watches.cloudscraper.create_scraper", return_value=mock_scraper):
        result = fetch_swisstimehouse("https://www.swisstimehouse.com/casio-good")

    assert result is not None
    assert result["name"] == "Casio Good"
    assert result["brand"] == "Casio"
    assert result["reference"] == "G999"
    assert result["price"] == 12345.0


def test_fetch_swisstimehouse_returns_none_on_unparseable_price():
    from utils.watches import fetch_swisstimehouse

    html = '''
    <html><head>
    <script type="application/ld+json">
    {"@type": "Product", "name": "Weird", "sku": "Z", "offers": {"price": "not-a-number"}}
    </script>
    </head><body></body></html>
    '''
    mock_scraper = _mock_scraper_returning(html)
    with patch("utils.watches.cloudscraper.create_scraper", return_value=mock_scraper):
        result = fetch_swisstimehouse("https://www.swisstimehouse.com/weird")
    assert result is None
