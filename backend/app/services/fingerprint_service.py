"""
Composite SHA-256 fingerprinting for error patterns.

Generates a deterministic hash from error_class + scrubbed_message + bucket_id
so that identical errors always resolve to the same fingerprint regardless of
when or where they occur.

All code paths that INSERT into error_patterns / triage_signals must use
generate_fingerprint() — do not duplicate the hash formula elsewhere.
"""

import hashlib


def generate_fingerprint(
    error_class: str,
    scrubbed_message: str,
    bucket_id: int,
) -> str:
    """Return a 64-char hex SHA-256 digest."""
    raw = f"{error_class}|{scrubbed_message}|{bucket_id}"
    return hashlib.sha256(raw.encode()).hexdigest()
