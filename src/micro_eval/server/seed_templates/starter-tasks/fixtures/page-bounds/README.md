# page-bounds

Fix `page_bounds()` in `page_bounds.py` so the last (partial) page, and
any page beyond the available range, clamp both bounds to `total` instead
of returning indexes past the end of the collection.

Run `python -m unittest discover -s tests` to check your fix. Do not edit `tests/`.
