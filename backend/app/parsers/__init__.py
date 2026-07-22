from app.parsers.detector import detect_bank_format
from app.parsers.revolut import parse_revolut_fr, parse_revolut_en
from app.parsers.ca import parse_credit_agricole
from app.parsers.leumi import parse_leumi

__all__ = ["detect_bank_format", "parse_revolut_fr", "parse_revolut_en", "parse_credit_agricole", "parse_leumi"]
