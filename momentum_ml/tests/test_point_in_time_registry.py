import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from point_in_time_registry import corporate_actions, listing_intervals


HTML = """
<table>
<tr><th>År</th><th>Kommentarer</th></tr>
<tr><td></td><td>Aktien är avnoterad</td></tr>
<tr><td>2024</td><td>Avnoterad från Nasdaq den 13 augusti</td></tr>
<tr><td>2018</td><td>Ny notering på First North den 2 maj</td></tr>
</table>
<table>
<tr><th>År</th><th>Villkor</th><th>1:a dag exkl. em.rätt/efter split</th></tr>
<tr><td>2021</td><td>S 1:100</td><td>16/7</td></tr>
<tr><td>2020</td><td>N 2:1, kurs 5 kr</td><td>3/10</td></tr>
</table>
"""


def test_extracts_dated_split_and_issue():
    rows = corporate_actions(HTML, "TEST.ST", "https://example.test")
    by_type = {row["event_type"]: row for row in rows}
    assert by_type["split"]["event_date"] == "2021-07-16"
    assert by_type["new_issue"]["event_date"] == "2020-10-03"
    assert by_type["delisting"]["event_date"] == "2024-08-13"


def test_listing_intervals_are_closed_by_delisting():
    fact = {
        "ticker": "TEST.ST", "name": "Test", "status": "avnoterad",
        "events": [
            {"date": "2024-08-13", "type": "avnotering"},
            {"date": "2018-05-02", "type": "notering"},
        ],
    }
    assert listing_intervals(fact)[0]["valid_from"] == "2018-05-02"
    assert listing_intervals(fact)[0]["valid_to"] == "2024-08-13"
