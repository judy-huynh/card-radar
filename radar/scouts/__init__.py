"""Scouts find listings. Every scout returns the same listing shape, so adding a market means adding one file.

Listing shape (all scouts):
  item_id, source, marketplace, title, url, image, price, currency, buying ("FIXED_PRICE,AUCTION"),
  seller, feedback, feedback_pct, item_country, item_location, created, ends, condition_raw,
  dest, ship, ship_currency      <- the shipping quote for the destination this search was made for
"""


class ScoutError(Exception):
    pass


class Job:
    def __init__(self, source, marketplace, dest, target, query, extra=None):
        self.source, self.marketplace, self.dest, self.target, self.query = source, marketplace, dest, target, query
        self.extra = extra or {}

    @property
    def scope(self):
        return f"{self.source}:{self.marketplace}:{self.dest}:{self.target['id']}"
