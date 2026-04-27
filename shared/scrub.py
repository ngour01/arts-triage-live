"""
Shared message scrubbing utility.

Single source of truth for cleaning IPs, hostnames, and hex codes from
error messages before fingerprinting. Used by the FastAPI triage service
and the seed_rules debug helper.
"""

import re


def scrub_message(message: str) -> str:
    """Normalize an error message by removing environment-specific tokens.

    Preserves PSOD / core-dump text verbatim so product crashes stay
    distinguishable.  Everything else gets IPs, hostnames, hex addresses,
    and ANSI codes stripped out.
    """
    if not message:
        return "N/A"
    msg = str(message)
    # Strip ANSI escape sequences
    msg = re.sub(r'\x1b\[[0-9;]*m', '', msg)
    # Preserve PSOD / core dump messages verbatim
    if "PSOD" in msg.upper() or "CORE" in msg.upper():
        return msg.strip()
    # Scrub environment-specific tokens
    msg = re.sub(r'Invalid test:\s+test-vpx-[\w\-]+', 'Invalid test: <TEST_SPEC>', msg)
    msg = re.sub(r'[\w\-]+\.(?:esx|vc)(?:[\.:]\d+)?', '<HOST>', msg)
    msg = re.sub(r'\d{1,3}(\.\d{1,3}){3}', '<IP>', msg)
    msg = re.sub(r'0x[0-9a-fA-F]+', '<HEX>', msg)
    return msg.strip()
