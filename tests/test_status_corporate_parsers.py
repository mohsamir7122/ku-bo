from __future__ import annotations

import unittest

from kubo.status_corporate_parsers import (
    StatusCorporateParserDriftError,
    parse_boursa_corporate_actions_html,
    parse_boursa_delisted_companies_html,
    parse_boursa_suspended_companies_html,
)


SUSPENDED_HTML = b"""
<html><body><table>
<tr><th>#No</th><th>Sec. Code</th><th>Ticker</th><th>Name</th><th>Sector</th><th>Market Segment</th></tr>
<tr><td>1</td><td>108</td><td>KFH</td><td>Kuwait Finance House</td><td>Banks</td><td>Premier</td></tr>
</table></body></html>
"""

EMPTY_SUSPENDED_HTML = b"""
<html><body><table>
<tr><th>#No</th><th>Sec. Code</th><th>Ticker</th><th>Name</th><th>Sector</th><th>Market Segment</th></tr>
</table></body></html>
"""

DELISTED_HTML = b"""
<html><body><table>
<tr><th>#No</th><th>Sec. Code</th><th>Ticker</th><th>Name</th><th>Sector</th><th>Market Segment</th><th>Date of Delisting</th></tr>
<tr><td>1</td><td>999</td><td>OLDCO</td><td>Old Company</td><td>Services</td><td>Main</td><td>30-06-2020</td></tr>
</table></body></html>
"""

CORPORATE_ACTIONS_HTML = b"""
<html><body><table>
<tr><th>ISIN Code</th><th>Sec. Code</th><th>Ticker</th><th>Cum-Dividend Date</th><th>Ex-Dividend Date</th><th>Record Date</th><th>Payment Date</th></tr>
<tr><td>KW0EQ0100010</td><td>101</td><td>NBK</td><td>2026-03-10</td><td>2026-03-11</td><td>2026-03-13</td><td>2026-03-20</td></tr>
<tr><td>KW0EQ0100085</td><td>108</td><td>KFH</td><td>Aug 10, 2026</td><td>Aug 11, 2026</td><td>Aug 13, 2026</td><td>Aug 18, 2026</td></tr>
</table></body></html>
"""


class StatusCorporateParserTests(unittest.TestCase):
    def test_suspended_companies_parser(self) -> None:
        rows = parse_boursa_suspended_companies_html(SUSPENDED_HTML)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].security_code, "108")
        self.assertEqual(rows[0].ticker, "KFH")

    def test_rendered_empty_suspended_table_is_observed_zero(self) -> None:
        self.assertEqual(
            parse_boursa_suspended_companies_html(EMPTY_SUSPENDED_HTML),
            (),
        )

    def test_delisted_companies_parser_reads_official_date(self) -> None:
        rows = parse_boursa_delisted_companies_html(DELISTED_HTML)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].delisting_date.isoformat(), "2020-06-30")

    def test_corporate_action_schedule_parser(self) -> None:
        rows = parse_boursa_corporate_actions_html(CORPORATE_ACTIONS_HTML)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].security_code, "101")
        self.assertEqual(rows[0].ex_date.isoformat(), "2026-03-11")
        self.assertEqual(rows[1].payment_date.isoformat(), "2026-08-18")

    def test_corporate_action_date_order_fails_closed(self) -> None:
        changed = CORPORATE_ACTIONS_HTML.replace(
            b"2026-03-10</td><td>2026-03-11",
            b"2026-03-12</td><td>2026-03-11",
        )
        with self.assertRaisesRegex(
            StatusCorporateParserDriftError,
            "CORPORATE_ACTION_DATE_ORDER",
        ):
            parse_boursa_corporate_actions_html(changed)

    def test_unrendered_status_page_fails_closed(self) -> None:
        with self.assertRaisesRegex(
            StatusCorporateParserDriftError,
            "REQUIRED_STATUS_CORPORATE_TABLE_NOT_FOUND",
        ):
            parse_boursa_suspended_companies_html(
                b"<html><body><div id='client-app'></div></body></html>"
            )


if __name__ == "__main__":
    unittest.main()
