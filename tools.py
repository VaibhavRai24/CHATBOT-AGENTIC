
from __future__ import annotations

import os
import math
import requests
from typing import Dict, Any, List, Optional
from langchain_core.tools import tool

DEFAULT_TIMEOUT = 12  # seconds

class ToolError(Exception):
    pass

def _get_json(url: str, params: Optional[Dict[str, Any]] = None) -> Any:
    try:
        r = requests.get(url, params=params or {}, timeout=DEFAULT_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        raise ToolError(f"HTTP error for {url}: {e}") from e
    except ValueError as e:
        raise ToolError(f"Bad JSON from {url}: {e}") from e


@tool
def get_weather(location: str, days: int = 1) -> Dict[str, Any]:
    """
    Get current weather and up to 7-day daily forecast for a place.

    Args:
        location: City/town/village name, e.g., "Bengaluru" or "New York".
        days: Number of days of forecast (1..7). Defaults to 1.

    Returns:
        A dict containing normalized current and daily forecast data, including
        resolved coordinates and timezone.
    """
    if not location or not location.strip():
        raise ToolError("Please provide a non-empty location string.")
    days = max(1, min(int(days), 7))
   
    geo = _get_json(
        "https://geocoding-api.open-meteo.com/v1/search",
        {"name": location, "count": 1, "language": "en", "format": "json"},
    )
    results = geo.get("results") or []
    if not results:
        raise ToolError(f"Location not found: {location}")
    place = results[0]
    lat = place["latitude"]
    lon = place["longitude"]
    resolved_name = place.get("name")
    country = place.get("country")
    timezone = place.get("timezone")

    # 2) Forecast
    forecast = _get_json(
        "https://api.open-meteo.com/v1/forecast",
        {
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,apparent_temperature,"
                       "precipitation,weather_code,wind_speed_10m",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,"
                     "sunrise,sunset,precipitation_sum",
            "forecast_days": days,
            "timezone": "auto",
        },
    )

    return {
        "query": {"location": location, "days": days},
        "resolved": {
            "name": resolved_name,
            "country": country,
            "latitude": lat,
            "longitude": lon,
            "timezone": timezone or forecast.get("timezone"),
        },
        "current": forecast.get("current"),
        "daily": forecast.get("daily"),
    }


@tool
def get_exchange_rate(base: str, target: str, amount: float = 1.0) -> Dict[str, Any]:
    """
    Convert an amount from one fiat currency to another using daily ECB rates.

    Args:
        base: Base currency code, e.g. "USD", "INR", "EUR".
        target: Target currency code, e.g. "EUR", "USD".
        amount: Amount to convert. Defaults to 1.0.

    Returns:
        A dict with rate, converted amount, and metadata (date, base, target).
    """
    if not base or not target:
        raise ToolError("Both 'base' and 'target' currency codes are required.")
    base = base.upper().strip()
    target = target.upper().strip()
    amount = float(amount)


    data = _get_json(
        "https://api.frankfurter.dev/v1/latest",
        {"base": base, "symbols": target},
    )
    rates = data.get("rates") or {}
    if target not in rates:
        raise ToolError(f"Unsupported currency pair {base}->{target}.")
    rate = float(rates[target])
    converted = amount * rate
    return {
        "base": base,
        "target": target,
        "amount": amount,
        "rate": rate,
        "converted": converted,
        "date": data.get("date"),
        "source": "ECB via Frankfurter",
    }

# --------------------------------------

@tool
def get_crypto_spot_price(symbol: str, currency: str = "USD") -> Dict[str, Any]:
    """
    Get the current spot price for a cryptocurrency pair from Coinbase.

    Args:
        symbol: Crypto ticker, e.g. "BTC", "ETH", "SOL".
        currency: Fiat currency code, e.g. "USD", "INR", "EUR". Defaults to "USD".

    Returns:
        A dict with the spot price (as a float string from Coinbase) and pair meta.
    """
    if not symbol:
        raise ToolError("Please provide a crypto 'symbol', e.g., BTC or ETH.")
    pair = f"{symbol.upper()}-{currency.upper()}"
    data = _get_json(f"https://api.coinbase.com/v2/prices/{pair}/spot")
    # Coinbase returns strings for amounts
    price = data.get("data", {}).get("amount")
    if price is None:
        raise ToolError(f"Pair not supported on Coinbase: {pair}")
    return {
        "pair": pair,
        "amount": float(price),
        "currency": data.get("data", {}).get("currency", currency.upper()),
        "source": "Coinbase",
    }


@tool
def get_public_holidays(year: int, country_code: str) -> List[Dict[str, Any]]:
    """
    Get all public holidays for a given year and ISO 3166-1 alpha-2 country code.

    Args:
        year: Year as integer, e.g., 2025.
        country_code: Country code like "IN", "US", "GB", "DE".

    Returns:
        A list of holiday dicts with date, localName, name, and types.
    """
    if not country_code or len(country_code.strip()) != 2:
        raise ToolError("Provide a valid ISO 3166-1 alpha-2 country code (e.g., IN, US).")
    country_code = country_code.upper()
    data = _get_json(f"https://date.nager.at/api/v3/PublicHolidays/{int(year)}/{country_code}")
    # Ensure minimal normalization
    holidays = []
    for h in data:
        holidays.append({
            "date": h.get("date"),
            "localName": h.get("localName"),
            "name": h.get("name"),
            "countryCode": h.get("countryCode", country_code),
            "types": h.get("types") or h.get("type"),
        })
    return holidays


@tool
def get_joke(category: str = "Programming", safe_mode: bool = True) -> Dict[str, Any]:
    """
    Get a random joke. Default category is 'Programming'.

    Args:
        category: One of 'Any', 'Programming', 'Misc', 'Pun', 'Spooky', 'Christmas', etc.
        safe_mode: If True, excludes potentially offensive content.

    Returns:
        A dict with 'type' and either 'joke' (single) or 'setup'/'delivery' (twopart).
    """
    cat = (category or "Any").replace(" ", "")
    params = {"type": "single"}  # one-liners are easier to present
    if safe_mode:
        params["safe-mode"] = ""
    data = _get_json(f"https://v2.jokeapi.dev/joke/{cat}", params=params)
    if data.get("error"):
        raise ToolError(f"JokeAPI error: {data}")
    if data.get("type") == "single":
        return {"type": "single", "joke": data.get("joke"), "category": data.get("category")}
    return {"type": "twopart", "setup": data.get("setup"), "delivery": data.get("delivery"),
            "category": data.get("category")}


@tool
def get_stock_price(symbol: str) -> Dict[str, Any]:
    """
    Get the latest stock price using AlphaVantage's GLOBAL_QUOTE.

    Requires an API key in ALPHAVANTAGE_API_KEY. Free keys are available.

    Args:
        symbol: Ticker symbol like "AAPL", "MSFT", "RELIANCE.BSE"

    Returns:
        A dict with price, change, and last trading day.
    """
    api_key = os.getenv("ALPHAVANTAGE_API_KEY")
    if not api_key:
        raise ToolError("Set ALPHAVANTAGE_API_KEY to use get_stock_price.")
    data = _get_json(
        "https://www.alphavantage.co/query",
        {"function": "GLOBAL_QUOTE", "symbol": symbol.upper(), "apikey": api_key},
    )
    quote = data.get("Global Quote") or data.get("globalQuote") or {}
    price = quote.get("05. price") or quote.get("price")
    change = quote.get("09. change") or quote.get("change")
    change_pct = quote.get("10. change percent") or quote.get("changePercent")
    if not price:
        raise ToolError(f"No quote returned for {symbol}.")
    return {
        "symbol": symbol.upper(),
        "price": float(price),
        "change": change,
        "change_percent": change_pct,
        "as_of": quote.get("07. latest trading day") or quote.get("latestTradingDay"),
        "source": "AlphaVantage",
    }
