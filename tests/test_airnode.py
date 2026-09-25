import copy
from http.client import HTTPConnection
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from airnode.auth import Auth
from airnode.config import DEFAULT, validate, receiver_args, write, read
from airnode.server import App, Handler
from airnode import broker

class ConfigTests(unittest.TestCase):
    def test_safe_defaults(self):
        args = receiver_args(DEFAULT)
        self.assertIn('--net-bind-address=127.0.0.1', args)
        self.assertIn('--net-bi-port=0', args)
        self.assertFalse(DEFAULT['feeders'])

    def test_location_optional_but_paired(self):
        value = copy.deepcopy(DEFAULT)
        value['receiver']['latitude'] = 10
        with self.assertRaises(ValueError): validate(value)
        value['receiver']['longitude'] = 20
        self.assertIn('--lat=10', receiver_args(value))

    def test_nonfinite_and_bool_rejected(self):
        for bad in [float('nan'), float('inf'), True, '20', -201, 201]:
            with self.subTest(bad=bad):
                value = copy.deepcopy(DEFAULT)
                value['receiver']['ppm'] = bad
                with self.assertRaises(ValueError): validate(value)

    def test_injection_and_unknown_keys_rejected(self):
        for bad in ['0; reboot', '--help', '$(id)', '../0', 'a b']:
            value = copy.deepcopy(DEFAULT)
            value['receiver']['device'] = bad
            # '--help' is valid literal serial, passed after --device=, never shell parsed.
            if bad == '--help':
                self.assertIn('--device=--help', receiver_args(value))
            else:
                with self.assertRaises(ValueError): validate(value)
        value = copy.deepcopy(DEFAULT)
        value['command'] = 'reboot'
        with self.assertRaises(ValueError): validate(value)

    def test_bad_feeders(self):
        for host in ['--help', 'a,b,beast_in', 'host;reboot', 'x\ny', '', 'x/../a']:
            value = copy.deepcopy(DEFAULT)
            value['feeders'] = [{'id':'test','host':host,'port':30004,'enabled':False}]
            with self.assertRaises(ValueError): validate(value)
        value = copy.deepcopy(DEFAULT)
        f = {'id':'test','host':'example.org','port':30004,'enabled':False}
        value['feeders'] = [f, f]
        with self.assertRaises(ValueError): validate(value)

    def test_atomic_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.json'
            write(path, DEFAULT)
            self.assertEqual(read(path), DEFAULT)
            with self.assertRaises(ValueError): write(path, {})
            self.assertEqual(read(path), DEFAULT)

class AuthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.auth = Auth(Path(self.temp.name) / 'auth.db')
        self.auth.password('very-long-test-password', initial=True)

    def test_password_verification(self):
        self.assertTrue(self.auth.verify('very-long-test-password'))
        self.assertFalse(self.auth.verify('wrong'))
        self.assertFalse(self.auth.verify(None))

    def test_setup_cannot_replace_owner(self):
        with self.assertRaises(ValueError): self.auth.password('replacement-password', initial=True)
        self.assertTrue(self.auth.verify('very-long-test-password'))

    def test_session_hash_expiry_and_logout(self):
        token, csrf = self.auth.session()
        self.assertEqual(self.auth.lookup(token), csrf)
        with self.auth.db() as db:
            self.assertNotEqual(db.execute('SELECT token FROM sessions').fetchone()[0], token)
        self.auth.logout(token)
        self.assertIsNone(self.auth.lookup(token))
        token, _ = self.auth.session()
        with patch('airnode.auth.time.time', return_value=time.time()+29000):
            self.assertIsNone(self.auth.lookup(token))

    def test_password_rotation_invalidates_sessions(self):
        token, _ = self.auth.session()
        self.auth.password('another-long-password')
        self.assertIsNone(self.auth.lookup(token))

    def test_persistent_throttling(self):
        for _ in range(8): self.assertTrue(self.auth.throttle('client'))
        self.assertFalse(Auth(self.auth.path).throttle('client'))
        self.assertTrue(self.auth.throttle('different-client'))

class APITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.app = App(cls.temp.name, demo=True)
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.server.app = cls.app
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.server.server_address[1]
        cls.password = 'airnode-test-password'
        status, headers, body = cls.request('POST', '/api/setup', {'token':cls.app.setup_path.read_text(), 'password':cls.password})
        assert status == 200, body
        cls.cookie = headers['Set-Cookie'].split(';')[0]
        cls.csrf = body['csrf']

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.temp.cleanup()

    @classmethod
    def request(cls, method, path, body=None, headers=None):
        conn = HTTPConnection('127.0.0.1', cls.port, timeout=5)
        h = {'Content-Type':'application/json'}
        h.update(headers or {})
        conn.request(method, path, body=None if body is None else json.dumps(body), headers=h)
        response = conn.getresponse()
        data = response.read()
        result = json.loads(data) if response.getheader('Content-Type').startswith('application/json') else data
        code, headers = response.status, dict(response.getheaders())
        conn.close()
        return code, headers, result

    def auth_headers(self):
        return {'Cookie':self.cookie, 'X-CSRF-Token':self.csrf}

    def test_private_endpoints_require_auth(self):
        for path in ['/api/config','/api/aircraft','/api/status','/api/logs']:
            self.assertEqual(self.request('GET', path)[0], 401)

    def test_csrf_required(self):
        self.assertEqual(self.request('POST','/api/config',DEFAULT,{'Cookie':self.cookie})[0],403)

    def test_cross_origin_rejected(self):
        h = self.auth_headers(); h['Origin']='https://evil.example'
        self.assertEqual(self.request('POST','/api/config',DEFAULT,h)[0],403)

    def test_mutating_get_not_allowed(self):
        self.assertEqual(self.request('GET','/api/power',headers=self.auth_headers())[0],404)

    def test_assets_and_security_headers(self):
        code, headers, body = self.request('GET','/')
        self.assertEqual(code,200)
        self.assertIn(b'AirNode', body)
        self.assertIn("frame-ancestors 'none'",headers['Content-Security-Policy'])
        self.assertEqual(headers['X-Content-Type-Options'],'nosniff')

    def test_path_traversal_rejected(self):
        self.assertEqual(self.request('GET','/../../airnode/server.py')[0],404)

    def test_authenticated_live_data(self):
        code, _, body=self.request('GET','/api/aircraft',headers=self.auth_headers())
        self.assertEqual(code,200)
        self.assertTrue(body['demo'])
        self.assertGreater(len(body['aircraft']),0)

    def test_invalid_config_no_mutation(self):
        before=read(self.app.config)
        self.assertEqual(self.request('POST','/api/config',{'bad':1},self.auth_headers())[0],400)
        self.assertEqual(read(self.app.config),before)

    def test_power_password_required(self):
        self.assertEqual(self.request('POST','/api/power',{'action':'reboot'},self.auth_headers())[0],403)

    def test_demo_service_stop_and_start(self):
        for action, stale in [('stop', True), ('start', False)]:
            code, _, _ = self.request('POST','/api/service',{'unit':'airnode-receiver','action':action},self.auth_headers())
            self.assertEqual(code,200)
            self.assertEqual(self.app.aircraft()['stale'],stale)

    def test_setup_token_consumed(self):
        self.assertFalse(self.app.setup_path.exists())
        self.assertEqual(self.request('POST','/api/setup',{'token':'anything','password':self.password})[0],409)

class DataTests(unittest.TestCase):
    def test_missing_corrupt_and_stale_receiver_data(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'config.json'
            write(config, DEFAULT)
            app = App(directory, data=directory, config=config)
            self.assertTrue(app.aircraft()['stale'])
            path = Path(directory) / 'aircraft.json'
            path.write_text('{bad')
            self.assertTrue(app.aircraft()['stale'])
            path.write_text(json.dumps({'now':time.time()-60,'aircraft':[],'messages':0}))
            self.assertTrue(app.aircraft()['stale'])
            path.write_text(json.dumps({'now':time.time(),'aircraft':[],'messages':0}))
            self.assertFalse(app.aircraft()['stale'])

class BrokerTests(unittest.TestCase):
    def test_arbitrary_unit_rejected(self):
        with patch.object(broker, 'read', return_value=copy.deepcopy(DEFAULT)), patch.object(broker, 'command') as command:
            for name in ['ssh','nginx','airnode-api','airnode-receiver;reboot','../../etc/passwd']:
                with self.assertRaises(ValueError): broker.dispatch({'op':'service','unit':name,'action':'restart'})
            command.assert_not_called()

    def test_arbitrary_action_rejected(self):
        with patch.object(broker, 'read', return_value=copy.deepcopy(DEFAULT)), patch.object(broker, 'command') as command:
            with self.assertRaises(ValueError): broker.dispatch({'op':'service','unit':'airnode-receiver','action':'enable'})
            command.assert_not_called()

    def test_service_uses_fixed_argument_list(self):
        with patch.object(broker, 'read', return_value=copy.deepcopy(DEFAULT)), patch.object(broker, 'command') as command:
            broker.dispatch({'op':'service','unit':'airnode-receiver','action':'restart'})
            command.assert_called_once_with(['systemctl','restart','airnode-receiver.service'])

    def test_power_allowlist_and_delay(self):
        with patch.object(broker, 'command') as command:
            with self.assertRaises(ValueError): broker.dispatch({'op':'power','action':'reboot;id'})
            command.assert_not_called()
            broker.dispatch({'op':'power','action':'reboot'})
            command.assert_called_once_with(['shutdown','-r','+1'])

    def test_hostname_injection(self):
        with patch.object(broker, 'command') as command:
            for name in ['$(id)', 'bad;reboot', 'a\nb', '-bad', 'bad.', 'x'*64, '']:
                with self.assertRaises(ValueError): broker.dispatch({'op':'hostname','hostname':name})
            command.assert_not_called()

    def test_reconcile_removed_disabled_and_new_feeds(self):
        old=copy.deepcopy(DEFAULT);new=copy.deepcopy(DEFAULT)
        old['feeders']=[{'id':'old','host':'a.example','port':30004,'enabled':True}]
        new['feeders']=[{'id':'new','host':'b.example','port':30004,'enabled':True}]
        with patch.object(broker,'command') as command:
            broker.reconcile(old,new)
            self.assertEqual(command.call_args_list[0].args[0],['systemctl','disable','--now','airnode-feeder@old.service'])
            self.assertEqual(command.call_args_list[-1].args[0],['systemctl','restart','airnode-feeder@new.service'])

if __name__ == '__main__':
    unittest.main()
