import ipaddress
import socket
from urllib.parse import urlparse


def validate_public_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("资料链接必须是公开的 http(s) URL")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, None)
        for item in addresses:
            address = ipaddress.ip_address(item[4][0])
            if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved:
                raise ValueError("不允许抓取内网或本机地址")
    except socket.gaierror as exc:
        raise ValueError("无法解析资料链接域名") from exc
    return value
