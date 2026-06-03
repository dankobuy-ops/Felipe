import ipaddress
import sys
import urllib.parse

BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]

ALLOWED_SCHEMES = {"http", "https"}


def validate(url: str) -> None:
    parsed = urllib.parse.urlparse(url)

    if parsed.scheme not in ALLOWED_SCHEMES:
        raise ValueError(f"Scheme '{parsed.scheme}' not allowed. Use http or https.")

    host = parsed.hostname
    if not host:
        raise ValueError("URL has no hostname.")

    # Block bare IP addresses in private/loopback ranges (SSRF guard)
    try:
        addr = ipaddress.ip_address(host)
        for net in BLOCKED_NETWORKS:
            if addr in net:
                raise ValueError(f"Target IP {addr} is in a blocked private range.")
    except ValueError as e:
        # ip_address() raises ValueError for hostnames — that's fine, let DNS resolve at runtime
        if "blocked private range" in str(e):
            raise


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: validate_inputs.py <target_url>")
        sys.exit(1)
    try:
        validate(sys.argv[1])
        print(f"OK: {sys.argv[1]}")
    except ValueError as e:
        print(f"INVALID: {e}", file=sys.stderr)
        sys.exit(1)
