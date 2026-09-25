import json
import unittest
from airnode.network import access_info

class AccessTests(unittest.TestCase):
    def test_real_addresses_and_ipv6_brackets(self):
        data = json.dumps([{'ifname':'eth0','operstate':'UP','addr_info':[
            {'scope':'global','local':'192.168.1.42'},
            {'scope':'global','local':'fd12::42'},
            {'scope':'link','local':'fe80::1'}]}])
        result = access_info('airnode', data)
        self.assertEqual(result['hostname_url'], 'https://airnode.local/')
        self.assertEqual([a['url'] for a in result['addresses']], ['https://192.168.1.42/', 'https://[fd12::42]/'])

    def test_demo_never_advertises_development_host_as_pi(self):
        self.assertEqual(access_info('airnode', '[]', True), {'hostname_url':None,'addresses':[],'demo':True})

    def test_inactive_loopback_and_container_addresses_excluded(self):
        data = json.dumps([{'ifname':name,'operstate':state,'addr_info':[{'scope':'global','local':ip}]}
                           for name,state,ip in [('lo','UP','127.0.0.1'),('docker0','UP','172.17.0.1'),('eth0','DOWN','192.168.1.2')]])
        self.assertEqual(access_info('airnode',data)['addresses'], [])

    def test_invalid_hostname_and_bad_network_data_safe(self):
        for value in ('{bad', 'null', '{}', '[{"addr_info":null}]'):
            self.assertEqual(access_info('bad/host',value)['addresses'], [])
        self.assertIsNone(access_info('bad/host','[]')['hostname_url'])
