"""
Normalizer package.

Exposes top-level normalize_* functions used across the pipeline.
"""
from data_transformer.normalizers.email import normalize_email
from data_transformer.normalizers.phone import normalize_phone
from data_transformer.normalizers.name import normalize_name
from data_transformer.normalizers.company import normalize_company
from data_transformer.normalizers.skills import normalize_skill
from data_transformer.normalizers.date import normalize_date
from data_transformer.normalizers.location import normalize_location_string, normalize_country, parse_location

__all__ = [
    "normalize_email",
    "normalize_phone",
    "normalize_name",
    "normalize_company",
    "normalize_skill",
    "normalize_date",
    "normalize_location_string",
    "normalize_country",
    "parse_location",
]
