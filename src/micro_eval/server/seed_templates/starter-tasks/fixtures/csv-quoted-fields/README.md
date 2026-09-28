# csv-quoted-fields

Fix `parse_csv_line()` in `csv_quoted_fields.py` so it correctly splits a
CSV line that contains double-quoted fields, embedded commas, and `""`
escaped quotes.

Run `python -m unittest discover -s tests` to check your fix. Do not edit `tests/`.
