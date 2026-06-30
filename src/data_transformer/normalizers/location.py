"""
Location normalization.

Parses free-text location strings into structured {city, region, country}
and normalizes country names to ISO-3166 alpha-2 codes.
"""
from __future__ import annotations

import re
from typing import Optional, Tuple

# ─── ISO-3166 alpha-2 lookup (common names → code) ───────────────────────────
COUNTRY_ALIASES: dict[str, str] = {
    # Full names
    "united states": "US", "united states of america": "US", "usa": "US", "us": "US",
    "united kingdom": "GB", "uk": "GB", "great britain": "GB",
    "canada": "CA", "ca": "CA",
    "australia": "AU", "au": "AU",
    "india": "IN", "in": "IN",
    "germany": "DE", "de": "DE", "deutschland": "DE",
    "france": "FR", "fr": "FR",
    "netherlands": "NL", "nl": "NL", "the netherlands": "NL", "holland": "NL",
    "singapore": "SG", "sg": "SG",
    "brazil": "BR", "br": "BR",
    "mexico": "MX", "mx": "MX",
    "spain": "ES", "es": "ES",
    "italy": "IT", "it": "IT",
    "sweden": "SE", "se": "SE",
    "norway": "NO", "no": "NO",
    "denmark": "DK", "dk": "DK",
    "finland": "FI", "fi": "FI",
    "switzerland": "CH", "ch": "CH",
    "austria": "AT", "at": "AT",
    "poland": "PL", "pl": "PL",
    "russia": "RU", "ru": "RU",
    "china": "CN", "cn": "CN",
    "japan": "JP", "jp": "JP",
    "south korea": "KR", "korea": "KR", "kr": "KR",
    "israel": "IL", "il": "IL",
    "new zealand": "NZ", "nz": "NZ",
    "ireland": "IE", "ie": "IE",
    "portugal": "PT", "pt": "PT",
    "belgium": "BE", "be": "BE",
    "argentina": "AR", "ar": "AR",
    "chile": "CL", "cl": "CL",
    "colombia": "CO", "co": "CO",
    "south africa": "ZA", "za": "ZA",
    "nigeria": "NG", "ng": "NG",
    "kenya": "KE", "ke": "KE",
    "uae": "AE", "ae": "AE", "united arab emirates": "AE",
    "saudi arabia": "SA", "sa": "SA",
    "egypt": "EG", "eg": "EG",
    "turkey": "TR", "tr": "TR",
    "pakistan": "PK", "pk": "PK",
    "bangladesh": "BD", "bd": "BD",
    "vietnam": "VN", "vn": "VN",
    "thailand": "TH", "th": "TH",
    "indonesia": "ID", "id": "ID",
    "malaysia": "MY", "my": "MY",
    "philippines": "PH", "ph": "PH",
    "taiwan": "TW", "tw": "TW",
    "hong kong": "HK", "hk": "HK",
}

# US state abbreviation → keep as-is (they are already region codes)
US_STATES = {
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN",
    "IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV",
    "NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN",
    "TX","UT","VT","VA","WA","WV","WI","WY","DC"
}


def normalize_country(raw: str) -> Optional[str]:
    """Map a country name/alias to ISO-3166 alpha-2, or return None if unrecognized."""
    if not raw:
        return None
    clean = raw.strip().lower()
    # Direct lookup
    if clean in COUNTRY_ALIASES:
        return COUNTRY_ALIASES[clean]
    # Already a valid 2-letter code?
    if len(raw.strip()) == 2 and raw.strip().upper() in COUNTRY_ALIASES.values():
        return raw.strip().upper()
    return None


def parse_location(raw: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Parse a free-text location into (city, region, country).

    Handles common patterns:
      "San Francisco, CA"          → (San Francisco, CA, US)
      "London, UK"                 → (London, None, GB)
      "Berlin, Germany"            → (Berlin, None, DE)
      "New York, NY, US"           → (New York, NY, US)
      "Remote"                     → (None, None, None)
      "India"                      → (None, None, IN)
    """
    if not raw:
        return None, None, None

    raw = raw.strip()

    # Split on comma
    parts = [p.strip() for p in raw.split(",") if p.strip()]

    if not parts:
        return None, None, None

    city: Optional[str] = None
    region: Optional[str] = None
    country_code: Optional[str] = None

    if len(parts) == 1:
        # Could be just a country or just a city
        candidate = parts[0]
        code = normalize_country(candidate)
        if code:
            country_code = code
        elif candidate.upper() in US_STATES:
            region = candidate.upper()
            country_code = "US"
        else:
            city = candidate

    elif len(parts) == 2:
        city = parts[0]
        second = parts[1].strip()
        # Is second part a US state abbreviation?
        if second.upper() in US_STATES:
            region = second.upper()
            country_code = "US"
        else:
            # Is it a country?
            code = normalize_country(second)
            if code:
                country_code = code
            else:
                # Could be a non-US region; keep as region
                region = second

    elif len(parts) >= 3:
        city = parts[0]
        region = parts[1].strip()
        # Last part is usually country
        code = normalize_country(parts[-1])
        if code:
            country_code = code
        else:
            # Try to interpret region as state
            if region.upper() in US_STATES:
                country_code = "US"

    return city, region, country_code


def normalize_location_string(raw: str) -> dict:
    """
    Return a dict with city, region, country, formatted keys.
    """
    city, region, country = parse_location(raw)
    parts = [p for p in [city, region, country] if p]
    formatted = ", ".join(parts) if parts else (raw.strip() or None)
    return {
        "city": city,
        "region": region,
        "country": country,
        "formatted": formatted,
    }
