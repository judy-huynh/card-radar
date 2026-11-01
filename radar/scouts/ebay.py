"""eBay scout: official Browse API, newest listings first, one search per target x marketplace x ship-to destination."""
import base64, json, time, urllib.error, urllib.parse, urllib.request
from . import Job, ScoutError

TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
ITEM_URL = "https://api.ebay.com/buy/browse/v1/item/"
NAME = "ebay"


class EbayScout:
    name = NAME

    def __init__(self, client_id, secret, settings):
        self.client_id, self.secret, self.cfg = client_id, secret, settings["ebay"]
        self.destinations = settings["destinations"]
        self._token = None

    def plan(self, targets):
        jobs = []
        for mp in self.cfg["marketplaces"]:
            for dest in mp["dests"]:
                for t in targets:
                    if t.get("paused"):
                        continue
                    for q in t["queries"]:
                        jobs.append(Job(NAME, mp["id"], dest, t, q, {"category_ids": mp.get("category_ids")}))
        return jobs

    def token(self):
        if self._token:
            return self._token
        auth = base64.b64encode(f"{self.client_id}:{self.secret}".encode()).decode()
        body = urllib.parse.urlencode({"grant_type": "client_credentials",
                                       "scope": "https://api.ebay.com/oauth/api_scope"}).encode()
        req = urllib.request.Request(TOKEN_URL, data=body, headers={
            "Authorization": f"Basic {auth}", "Content-Type": "application/x-www-form-urlencoded"})
        # eBay's sign-in occasionally rejects good keys for a moment; only a repeated refusal is a real failure
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=20) as r:
                    self._token = json.load(r)["access_token"]
                return self._token
            except urllib.error.HTTPError as e:
                err = f"eBay sign-in failed ({e.code}): {e.read()[:200].decode(errors='ignore')}"
                if attempt < 2:
                    time.sleep(5 * (attempt + 1))
        raise ScoutError(err)

    def run(self, job):
        d = self.destinations[job.dest]
        params = {"q": job.query, "limit": str(self.cfg.get("limit", 200)), "sort": "newlyListed",
                  "filter": f"deliveryCountry:{d['country']},buyingOptions:{{FIXED_PRICE|BEST_OFFER|AUCTION}}"}
        if job.extra.get("category_ids"):
            params["category_ids"] = job.extra["category_ids"]
        ctx = urllib.parse.quote(f"country={d['country']},zip={d['postal']}")
        req = urllib.request.Request(SEARCH_URL + "?" + urllib.parse.urlencode(params), headers={
            "Authorization": f"Bearer {self.token()}", "X-EBAY-C-MARKETPLACE-ID": job.marketplace,
            "X-EBAY-C-ENDUSERCTX": f"contextualLocation={ctx}", "Accept-Language": "en-US"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.load(r)
        except urllib.error.HTTPError as e:
            raise ScoutError(f"{job.marketplace} search failed ({e.code}): {e.read()[:200].decode(errors='ignore')}")
        except urllib.error.URLError as e:
            raise ScoutError(f"{job.marketplace} unreachable: {e.reason}")
        return [normalize(i, job) for i in data.get("itemSummaries", [])]

    def details(self, item_id, marketplace):
        """One listing's own record, which search results leave out or get wrong: the seller's "Card Condition" pick,
        and whether it's still for sale (search kept returning a Dark Gengar four days after it sold)."""
        req = urllib.request.Request(ITEM_URL + urllib.parse.quote(item_id), headers={
            "Authorization": f"Bearer {self.token()}", "X-EBAY-C-MARKETPLACE-ID": marketplace, "Accept-Language": "en-US"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                return {"seller_condition": None, "gone": "Listing ended or removed on eBay"}
            raise ScoutError(f"{marketplace} item {item_id} failed: {e}")
        except urllib.error.URLError as e:
            raise ScoutError(f"{marketplace} item {item_id} failed: {e.reason}")
        cond = next((d for d in data.get("conditionDescriptors") or [] if d.get("values")), None)
        return {"seller_condition": cond["values"][0].get("content") if cond else None, "gone": gone_reason(data)}


def gone_reason(data, now=None):
    """Why a listing can't be bought any more, or None while it's for sale."""
    av = (data.get("estimatedAvailabilities") or [{}])[0]
    end = data.get("itemEndDate")
    when = time.strftime(" on %b %d", time.strptime(end[:10], "%Y-%m-%d")) if end else ""
    if av.get("estimatedAvailabilityStatus") == "OUT_OF_STOCK":
        return f"Sold on eBay{when}" if av.get("estimatedSoldQuantity") else "Out of stock on eBay"
    if end and end[:19] < (now or time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())):
        return f"Listing ended{when}"
    return None


def normalize(it, job):
    price = it.get("price") or it.get("currentBidPrice") or {}
    seller = it.get("seller", {})
    ship = (it.get("shippingOptions") or [{}])[0]
    cost = ship.get("shippingCost") or {}
    loc = it.get("itemLocation", {})
    pct = seller.get("feedbackPercentage")
    return {
        "item_id": it["itemId"], "source": NAME, "marketplace": job.marketplace, "target_id": job.target["id"],
        "title": it.get("title", ""), "url": it.get("itemWebUrl"), "image": (it.get("image") or {}).get("imageUrl"),
        "price": float(price.get("value", 0)), "currency": price.get("currency", "USD"),
        "buying": ",".join(it.get("buyingOptions", [])),
        "seller": None,   # never stored: no eBay user data kept, so we're exempt from account-deletion notices
        "feedback": seller.get("feedbackScore"),
        "feedback_pct": float(pct) if pct not in (None, "") else None,
        "item_country": loc.get("country"),
        "item_location": ", ".join(x for x in [loc.get("city"), loc.get("stateOrProvince"), loc.get("country")] if x),
        "created": it.get("itemCreationDate") or it.get("itemOriginDate"), "ends": it.get("itemEndDate"),
        "condition_raw": it.get("condition"),
        "dest": job.dest,
        "ship": float(cost["value"]) if cost.get("value") not in (None, "") else None,
        "ship_currency": cost.get("currency"),
    }
