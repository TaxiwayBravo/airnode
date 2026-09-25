"""Build local dashboard addresses from OS network observations, never guessed IPs."""
import ipaddress
import json
import re

def access_info(hostname, network, demo=False):
    if demo:
        return {'hostname_url': None, 'addresses': [], 'demo': True}
    host = hostname if isinstance(hostname, str) and re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9-]{0,62}', hostname) else None
    addresses = []
    try:
        interfaces = json.loads(network)
        for interface in interfaces:
            if interface.get('operstate') != 'UP' or interface.get('ifname', '').startswith(('lo', 'docker', 'veth', 'br-')):
                continue
            for entry in interface.get('addr_info', []):
                if entry.get('scope') != 'global':
                    continue
                ip = ipaddress.ip_address(entry.get('local', ''))
                if ip.is_loopback or ip.is_link_local or ip.is_unspecified or ip.is_multicast:
                    continue
                url = 'https://' + ('[' + str(ip) + ']' if ip.version == 6 else str(ip)) + '/'
                if not any(item['url'] == url for item in addresses):
                    addresses.append({'interface': interface['ifname'], 'address': str(ip), 'url': url})
    except (ValueError, TypeError, AttributeError, KeyError):
        pass
    return {'hostname_url': 'https://' + host + '.local/' if host else None, 'addresses': addresses, 'demo': False}
