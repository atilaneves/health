from datetime import date

from health import dexa


def test_rows_skip_comments_and_blank_values(tmp_path):
    p = tmp_path / "scans.csv"
    p.write_text("# a comment\ndate,total_kg,fat_kg,lean_kg,fat_pct,visceral_fat_kg\n"
                 "2026-06-22,72.9,13.8,55.9,18.9,\n")
    assert dexa.rows(p) == [(date(2026, 6, 22), 72.9, 13.8, 55.9, 18.9, None)]


def test_no_file_no_rows(tmp_path):
    assert dexa.rows(tmp_path / "missing.csv") == []
