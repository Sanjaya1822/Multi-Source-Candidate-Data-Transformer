"""
Phone number normalization to E.164 format.

Handles:
  - US numbers with or without country code: (415) 555-1234, +1-415-555-1234
  - International numbers: +91-9876543210, +44 20 7946 0958
  - Numbers with various separators: dots, dashes, spaces, parens
"""
from typing import Optional
import phonenumbers


# Regions to try when no country code is present, in priority order
_FALLBACK_REGIONS = ["US", "IN", "GB", "CA", "AU", "DE", "FR", "SG"]


def normalize_phone(phone: str, default_region: str = "US") -> Optional[str]:
    """
    Normalize a phone number string to E.164 format.

    Tries the default_region first, then a set of common international regions.
    Returns None if the number cannot be parsed as valid in any region.
    """
    if not phone:
        return None

    # Strip common non-numeric noise but preserve leading +
    cleaned = phone.strip()

    # Try direct parse (handles numbers with explicit country code like +91...)
    for region in ([default_region] + _FALLBACK_REGIONS):
        try:
            parsed = phonenumbers.parse(cleaned, region)
            if phonenumbers.is_valid_number(parsed):
                return phonenumbers.format_number(
                    parsed, phonenumbers.PhoneNumberFormat.E164
                )
        except phonenumbers.NumberParseException:
            continue

    return None
