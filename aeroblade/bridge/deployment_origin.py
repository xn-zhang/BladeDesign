"""Browser origins accepted for local, LAN and HTTPS deployments."""
import ipaddress
from urllib.parse import urlsplit

_LAN = tuple(ipaddress.ip_network(n) for n in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '127.0.0.0/8'))

def validate_public_origin(origin):
    parsed = urlsplit(origin)
    if (not parsed.hostname or parsed.path or parsed.query or parsed.fragment
            or parsed.username is not None or parsed.password is not None
            or any(c.isspace() for c in origin) or '?' in origin or '#' in origin
            or (parsed.port is not None and not 1 <= parsed.port <= 65535)):
        raise ValueError('AEROBLADE_PUBLIC_ORIGIN must be an origin without path, credentials, query or fragment')
    if parsed.scheme == 'https':
        return origin
    if parsed.scheme == 'http':
        if parsed.hostname in ('localhost', '::1'):
            return origin
        try:
            address = ipaddress.ip_address(parsed.hostname)
            if any(address in network for network in _LAN):
                return origin
        except ValueError:
            pass
    raise ValueError('AEROBLADE_PUBLIC_ORIGIN requires HTTPS or HTTP with a private IPv4 / loopback address')
