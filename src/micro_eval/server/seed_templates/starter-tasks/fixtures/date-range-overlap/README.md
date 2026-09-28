# date-range-overlap

Fix `overlaps()` in `date_range_overlap.py` so half-open date ranges
`[start, end)` only report an overlap when they actually share a day.

Run `python -m unittest discover -s tests` to check your fix. Do not edit `tests/`.
