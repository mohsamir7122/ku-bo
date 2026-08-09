from __future__ import annotations

import unittest

from kubo.official_parsers import (
    OfficialParserDriftError,
    parse_boursa_contact_weekdays_html,
    parse_boursa_listed_companies_html,
    parse_boursa_market_holidays_html,
    parse_boursa_trading_extension_html,
)


LISTED_HTML = b"""
<html><body>
<table>
<tr><th>#No</th><th>Sec. Code</th><th>Ticker</th><th>Name</th><th>Sector</th><th>Market Segment</th><th>Date of Listing</th></tr>
<tr><td>1</td><td>101</td><td>NBK</td><td>National Bank of Kuwait</td><td>Banks</td><td>Premier</td><td>29-09-1984</td></tr>
<tr><td>2</td><td>108</td><td>KFH</td><td>Kuwait Finance House</td><td>Banks</td><td>Premier</td><td>29/09/1984</td></tr>
</table>
</body></html>
"""

HOLIDAYS_HTML = b"""
<html><body><h2>Kuwait Public Holidays 2026</h2>
<table>
<tr><th>Month</th><th>Date</th><th>Vacation</th></tr>
<tr><td>January</td><td>1</td><td>New Year</td></tr>
<tr><td>February</td><td>25 - 26</td><td>National Day - Liberation Day</td></tr>
<tr><td>April</td><td>-</td><td>-</td></tr>
</table></body></html>
"""

EXTENSION_HTML = b"""
<html><body>
<h2>Starting October 12th, 2025</h2>
<p>The continuous trading session will run from 9:00 a.m. to 1:00 p.m.</p>
<p>The closing auction session will run from 1:00 p.m. to 1:10 p.m.</p>
<p>The trade at last session will run from 1:10 p.m. to 1:15 p.m.</p>
</body></html>
"""

CONTACT_HTML = b"""
<html><body><p>Trading Hours: 9:00 AM - 1:15 PM (Sunday - Thursday)</p></body></html>
"""


class OfficialParserTests(unittest.TestCase):
    def test_listed_companies_parser_reads_rendered_table(self) -> None:
        rows = parse_boursa_listed_companies_html(LISTED_HTML)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].security_code, "101")
        self.assertEqual(rows[0].ticker, "NBK")
        self.assertEqual(rows[0].listing_date.isoformat(), "1984-09-29")

    def test_market_holidays_expands_ranges(self) -> None:
        year, rows = parse_boursa_market_holidays_html(HOLIDAYS_HTML)
        self.assertEqual(year, 2026)
        self.assertEqual(
            [item.holiday_date.isoformat() for item in rows],
            ["2026-01-01", "2026-02-25", "2026-02-26"],
        )

    def test_trading_extension_parser_binds_effective_times(self) -> None:
        regime = parse_boursa_trading_extension_html(EXTENSION_HTML)
        self.assertEqual(regime.effective_from.isoformat(), "2025-10-12")
        self.assertEqual(regime.continuous_start, "09:00:00")
        self.assertEqual(regime.continuous_end, "13:00:00")
        self.assertEqual(regime.trade_at_last_end, "13:15:00")

    def test_contact_parser_reads_sunday_thursday(self) -> None:
        self.assertEqual(
            parse_boursa_contact_weekdays_html(CONTACT_HTML),
            frozenset({6, 0, 1, 2, 3}),
        )

    def test_unrendered_listed_page_fails_closed(self) -> None:
        with self.assertRaisesRegex(
            OfficialParserDriftError,
            "REQUIRED_OFFICIAL_TABLE_HEADERS_NOT_FOUND",
        ):
            parse_boursa_listed_companies_html(
                b"<html><body><div id='client-app'></div></body></html>"
            )


if __name__ == "__main__":
    unittest.main()
