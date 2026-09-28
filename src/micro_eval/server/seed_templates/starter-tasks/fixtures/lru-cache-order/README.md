# lru-cache-order

Fix `LRUCache` in `lru_cache_order.py` so `get()` refreshes recency, and
the correct (least recently used) key is evicted when capacity is
exceeded.

Run `python -m unittest discover -s tests` to check your fix. Do not edit `tests/`.
