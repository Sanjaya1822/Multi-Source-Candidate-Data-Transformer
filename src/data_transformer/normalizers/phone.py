"""
Phone number normalization.
"""
from typing import Optional
import phonenumbers


def normalize_phone(phone: str, default_region: str = "US") -> Optional[str]:
    """
    Normalize phone number to E.164 format.
    Returns None if the phone number is invalid.
    """
    if not phone:
        return None
        
    try:
        parsed = phonenumbers.parse(phone, default_region)
        if phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        pass
        
    return None
