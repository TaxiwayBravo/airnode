import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from airnode import maintenance as m, aggregators as ag
from airnode.aggregator_control import Manager

class SoftwareTests(unittest.TestCase):
    def test_untrusted_provider_cannot_reach_systemctl(self):
        command = Mock()
        for value in ('../../ssh', 'piaware;reboot', '', None):
            with self.assertRaises(ValueError): m.operate(command, value, 'install')
        command.assert_not_called()

    def test_install_is_nonblocking_and_allowlisted(self):
        command = Mock()
        m.operate(command, 'flightaware', 'install')
        command.assert_called_once_with(['systemctl', 'start', '--no-block', 'airnode-provider-software@flightaware.service'])
        command.reset_mock()
        with self.assertRaises(ValueError): m.operate(command, 'flightaware', 'purge')
        command.assert_not_called()

    def test_daily_toggle_controls_only_selected_timer(self):
        command = Mock()
        m.operate(command, 'flightradar24', 'auto-on')
        m.operate(command, 'flightradar24', 'auto-off')
        self.assertEqual(command.call_args_list[0].args[0], ['systemctl', 'enable', '--now', 'airnode-provider-software@flightradar24.timer'])
        self.assertEqual(command.call_args_list[1].args[0], ['systemctl', 'disable', '--now', 'airnode-provider-software@flightradar24.timer'])

    def test_cannot_schedule_missing_client(self):
        manager = Manager(Mock())
        with patch.object(manager, 'available', return_value=False):
            with self.assertRaises(ValueError): manager.operate('flightaware', 'auto-on')
        manager.command.assert_not_called()

    def test_status_distinguishes_busy_failed_and_version(self):
        for state, expected in [('ActiveState=activating\nResult=success', 'Working'), ('ActiveState=failed\nResult=exit-code', 'Failed')]:
            command = Mock(side_effect=[state, 'enabled', 'install ok installed|1.2.3'])
            value = m.software_status(command, 'flightaware')
            self.assertEqual(value['result'], expected)
            self.assertEqual(value['busy'], expected == 'Working')
            self.assertTrue(value['automatic'])
            self.assertEqual(value['version'], '1.2.3')

    def test_missing_package_is_not_presented_as_installed_version(self):
        value = m.software_status(Mock(side_effect=['', 'disabled', 'deinstall ok config-files|old']), 'flightaware')
        self.assertEqual(value['version'], '')

    def test_bootstrap_hash_mismatch_prevents_write(self):
        response = Mock(url='https://example.invalid/package')
        response.read.return_value = b'changed'
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        with tempfile.TemporaryDirectory() as directory, patch.object(m.urllib.request, 'urlopen', return_value=response):
            path = Path(directory) / 'package.deb'
            with self.assertRaises(ValueError): m.download('flightaware', path)
            self.assertFalse(path.exists())

    def test_insecure_redirect_is_rejected(self):
        response = Mock(url='http://example.invalid/package')
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        with patch.object(m.urllib.request, 'urlopen', return_value=response):
            with self.assertRaises(ValueError): m.download('flightaware', 'unused')
        response.read.assert_not_called()

    def test_verified_bootstrap_saved(self):
        data = b'verified fixture'
        response = Mock(url='https://example.invalid/package')
        response.read.return_value = data
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        with tempfile.TemporaryDirectory() as directory, patch.object(m.urllib.request, 'urlopen', return_value=response), patch.dict(m.BOOTSTRAPS, {'flightaware': ('https://example.invalid/package', hashlib.sha256(data).hexdigest())}):
            path = Path(directory) / 'package.deb'
            m.download('flightaware', path)
            self.assertEqual(path.read_bytes(), data)

    def test_worker_never_uses_shell_and_stdin_is_closed(self):
        with patch.object(m.subprocess, 'run', return_value=Mock(returncode=0)) as run:
            m.run(['apt-get', 'update'])
        self.assertNotIn('shell', run.call_args.kwargs)
        self.assertEqual(run.call_args.kwargs['stdin'], m.subprocess.DEVNULL)
        self.assertEqual(run.call_args.kwargs['env']['DEBIAN_FRONTEND'], 'noninteractive')

class NativeLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manager = Manager(Mock(return_value=''), self.root, self.root)
        self.marker = self.root / 'providers' / 'flightradar24.enabled'
        self.entry = {'enabled': False, 'credential': '0123456789abcdef'}

    def run_job(self, runner):
        with patch.object(m, 'ROOT', self.root), patch('airnode.aggregator_control.Manager', return_value=self.manager), patch.object(m, 'guard_native'), patch.object(m, 'repository'), patch.object(m, 'harden_native') as harden, patch.object(m, 'run', side_effect=runner), patch.object(self.manager, 'available', return_value=True), patch.object(self.manager, 'configure') as configure:
            m.native_job('flightradar24')
        return configure, harden

    def test_install_preserves_key_and_leaves_disabled_feed_off(self):
        ag.save(self.manager.path, {'flightradar24': self.entry})
        calls = []
        configure, harden = self.run_job(lambda args, **kw: calls.append(args))
        configure.assert_not_called()
        harden.assert_called_once()
        self.assertIn(['systemctl', 'disable', '--now', 'fr24feed.service'], calls)
        self.assertFalse(self.marker.exists())
        config = self.manager.target_path('flightradar24').read_text()
        self.assertIn(self.entry['credential'], config)
        self.assertIn('receiver="beast-tcp"', config)
        install = next(c for c in calls if c[0] == 'apt-get' and 'install' in c)
        self.assertEqual(install[-1], 'fr24feed')
        self.assertIn('--no-remove', install)

    def test_success_reapplies_only_previously_enabled_feed(self):
        self.entry['enabled'] = True
        ag.save(self.manager.path, {'flightradar24': self.entry})
        ag.atomic_text(self.marker, 'enabled')
        def runner(args, **kw):
            if args[0] == 'apt-get': self.assertFalse(self.marker.exists())
        configure, _ = self.run_job(runner)
        configure.assert_called_once_with({'provider': 'flightradar24', 'enabled': True, 'consent': True})

    def test_package_failure_does_not_reenable_sharing(self):
        self.entry['enabled'] = True
        ag.save(self.manager.path, {'flightradar24': self.entry})
        ag.atomic_text(self.marker, 'enabled')
        def fail(args, **kw):
            if args[0] == 'apt-get': raise ValueError('offline')
        with self.assertRaises(ValueError): self.run_job(fail)
        self.assertFalse(self.marker.exists())
        self.assertEqual(ag.load(self.manager.path)['flightradar24'], self.entry)

    def test_failure_redacts_logs(self):
        ag.save(self.manager.path, {'flightradar24': self.entry})
        command = Mock(return_value='key=' + self.entry['credential'])
        with patch.object(m, 'ROOT', self.root):
            result = m.operate(command, 'flightradar24', 'install-logs')
        self.assertNotIn(self.entry['credential'], result['text'])

    def test_disabling_missing_client_removes_boot_gate(self):
        ag.atomic_text(self.marker, 'enabled')
        ag.save(self.manager.path, {'flightradar24': {'enabled': True, 'credential': self.entry['credential']}})
        with patch.object(self.manager, 'available', return_value=False):
            self.manager.configure({'provider': 'flightradar24', 'enabled': False})
        self.assertFalse(self.marker.exists())
