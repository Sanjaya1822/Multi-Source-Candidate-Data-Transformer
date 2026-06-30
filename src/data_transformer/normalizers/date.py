"""
Date normalization.
"""
from typing import Optional
from dateutil import parser


def normalize_date(date_str: str) -> Optional[str]:
    """
    Normalize date string to YYYY-MM format.
    Returns None if the date cannot be parsed.
    """
    if not date_str:
        return None
        
    try:
        # Default to Jan 1st if only year is provided
        dt = parser.parse(date_str, default=parser.parse("2000-01-01"))
        return dt.strftime("%Y-%m")
    except (ValueError, TypeError, OverflowError):
        pass
        
    return None
