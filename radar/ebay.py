"""eBay Browse API: app token + item_summary search. Official API, no scraping."""
import base64, json, urllib.parse, urllib.request

TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
CURRENCY = {"EBAY_US": "USD", "EBAY_CA": "CAD"}

def get_token(client_id, secret):
    auth = base64.b64encode(f"{client_id}:{secret}".encode()).decode()
    body = urllib.parse.urlencode({"grant_type": "client_credentials",
                                   "scope": "https://api.ebay.com/oauth/api_scope"}).encode()
    req = urllib.request.Request(TOKEN_URL, data=body, headers={
        "Authorization": f"Basic {auth}", "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)["access_token"]

def search(token, marketplace, query, max_price, limit, fx_cad_per_usd=1.4):
    cur = CURRENCY[marketplace]
    cap = max_price if cur == "USD" else int(max_price * fx_cad_per_usd)
    params = {"q": query, "limit": str(limit), "sort": "price",
              "filter": f"price:[1..{cap}],priceCurrency:{cur},buyingOptions:{{FIXED_PRICE}}"}
    req = urllib.request.Request(SEARCH_URL + "?" + urllib.parse.urlencode(params), headers={
        "Authorization": f"Bearer {token}", "X-EBAY-C-MARKETPLACE-ID": marketplace})
    with urllib.request.urlopen(req, timeout=20) as r:
        return [normalize(i, marketplace) for i in json.load(r).get("itemSummaries", [])]

def normalize(it, marketplace):
    """Flatten an eBay item summary into the fields the store and dashboard use."""
    seller = it.get("seller", {})
    ship = (it.get("shippingOptions") or [{}])[0].get("shippingCost", {})
    loc = it.get("itemLocation", {})
    return {
        "item_id": it["itemId"], "marketplace": marketplace, "title": it.get("title", ""),
        "price": float(it["price"]["value"]), "currency": it["price"]["currency"],
        "shipping": float(ship["value"]) if ship.get("value") else None,
        "url": it.get("itemWebUrl"), "seller": seller.get("username"),
        "feedback": seller.get("feedbackScore"), "feedback_pct": seller.get("feedbackPercentage"),
        "condition": it.get("condition"), "location": ", ".join(x for x in [loc.get("city"), loc.get("country")] if x),
        "image": (it.get("image") or {}).get("imageUrl"),
    }
