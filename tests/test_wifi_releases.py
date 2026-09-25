import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import Mock, patch
from airnode import wifi, releases
from airnode.server import App, APIError

class WifiTests(unittest.TestCase):
    def test_password_and_ssid_validation(self):
        valid = {'ssid':'Home: Wi-Fi','password':'correct-password','country':'GB'}
        self.assertEqual(wifi.validate(valid), valid)
        for change in ({'ssid':'evil\n[ipv4]'}, {'ssid':'é'*17}, {'password':'short'}, {'country':'GB;id'}, {'command':'reboot'}):
            with self.assertRaises(ValueError): wifi.validate({**valid, **change})

    def test_keyfile_cannot_inject_sections(self):
        text = wifi.profile('Home space\\name', 'password\\123', 'uuid')
        self.assertIn('ssid=Home\\sspace\\\\name',text)
        self.assertIn('psk=password\\\\123',text)
        ap = wifi.profile('AirNode-Setup-123', 'password123', 'uuid', True)
        self.assertIn('mode=ap',ap)
        self.assertIn('method=shared',ap)
        self.assertIn('key-mgmt=wpa-psk',ap)
        self.assertIn('autoconnect=false',ap)

    def test_nmcli_escaping(self):
        self.assertEqual(wifi.fields(r'Home\:West:90:WPA2'),['Home:West','90','WPA2'])

    def test_queue_stores_secret_privately_without_executing_commands(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(wifi,'REQUEST',Path(temp)/'request.json'), patch.object(wifi,'command') as command:
            value={'ssid':'Home','password':'password123','country':'GB'}
            result=wifi.queue(value)
            self.assertNotIn(value['password'],json.dumps(result))
            self.assertEqual(json.loads(wifi.REQUEST.read_text()),value)
            with self.assertRaises(ValueError): wifi.queue(value)
            command.assert_not_called()

    def test_hotspot_is_not_treated_as_home_network(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(wifi,'ROOT',Path(temp)), patch.object(wifi,'STATE',Path(temp)/'state.json'), patch.object(wifi,'command',return_value='wlan0:wifi:connected:AirNode Setup'):
            state=wifi.snapshot()
            self.assertTrue(state['hotspot']);self.assertFalse(state['connected'])

    def test_failed_join_preserves_previous_profile_and_restores_hotspot(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);profiles=root/'profiles';profiles.mkdir()
            previous=profiles/'airnode-home-old.nmconnection';previous.write_text('existing')
            (root/'hotspot.json').write_text(json.dumps({'country':'GB','ssid':'Setup','password':'password123','uuid':'ap'}))
            def command(args,**kwargs):
                if 'up' in args: raise ValueError('Connection failed')
                return ''
            with patch.object(wifi,'ROOT',root),patch.object(wifi,'PROFILES',profiles),patch.object(wifi,'country_codes',return_value={'GB'}),patch.object(wifi,'command',side_effect=command) as run,patch.object(wifi,'hotspot_up') as restore,patch.object(wifi,'snapshot'):
                wifi.connect({'ssid':'Home','password':'private-password','country':'GB'})
            restore.assert_called_once()
            self.assertEqual(previous.read_text(),'existing')
            self.assertEqual(len(list(profiles.glob('*.nmconnection'))),1)
            self.assertNotIn('private-password',str(run.call_args_list))

class ReleaseTests(unittest.TestCase):
    def release(self, tag, prerelease=False):
        return {'tag_name':tag,'prerelease':prerelease,'draft':False,'assets':[
            {'name':name,'browser_download_url':'https://github.com/TaxiwayBravo/airnode/releases/download/'+tag+'/'+name}
            for name in ('airnode-update.tar.gz','airnode-release.json','airnode-release.sig')]}

    def test_stable_beta_selection_and_no_downgrade(self):
        stable=self.release('v0.5.0');beta=self.release('v0.6.0-beta.2',True)
        self.assertEqual(releases.choose([beta,stable],'stable','0.4.0')['tag_name'],'v0.5.0')
        self.assertEqual(releases.choose([beta,stable],'beta','0.4.0')['tag_name'],'v0.6.0-beta.2')
        self.assertIsNone(releases.choose([stable],'beta','0.6.0-beta.2'))
        self.assertGreater(releases.version('0.6.0'),releases.version('0.6.0-beta.99'))

    def test_draft_and_incomplete_releases_ignored(self):
        release=self.release('v1.0.0');release['draft']=True
        self.assertIsNone(releases.choose([release],'beta','0.1.0'))
        release['draft']=False;release['assets']=[]
        self.assertIsNone(releases.choose([release],'beta','0.1.0'))

    def test_fixed_repository_and_https_downloads(self):
        release=self.release('v1.0.0');self.assertEqual(len(releases.assets(release)),3)
        release['assets'][0]['browser_download_url']='https://example.com/malware.tar.gz'
        with self.assertRaises(ValueError): releases.assets(release)
        for url in ('http://github.com/a','https://github.com.evil.test/a','https://user:pass@github.com/a','https://127.0.0.1/a'):
            self.assertFalse(releases.trusted_url(url))

    def test_signature_failure_stops_manifest_use(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(releases.subprocess,'run',return_value=Mock(returncode=1)):
            with self.assertRaisesRegex(ValueError,'signature'): releases.verify_manifest(b'{}',b'bad','v1.0.0',temp)

    def test_unsafe_archive_members_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            archive=Path(temp)/'a.tar.gz'
            for name, kind in [('AirNode/../../escape',tarfile.REGTYPE),('/etc/passwd',tarfile.REGTYPE),('AirNode/link',tarfile.SYMTYPE)]:
                with tarfile.open(archive,'w:gz') as tar:
                    member=tarfile.TarInfo(name);member.type=kind;tar.addfile(member,io.BytesIO())
                with self.assertRaises(ValueError): releases.unpack(archive,Path(temp)/'out')

    def test_only_allowlisted_release_jobs(self):
        command=Mock()
        releases.operate(command,'install')
        command.assert_called_once_with(['systemctl','start','--no-block','airnode-release@install.service'])
        command.reset_mock()
        with self.assertRaises(ValueError): releases.operate(command,'install;id')
        command.assert_not_called()

    def test_interrupted_release_restores_directory_and_units(self):
        spec=importlib.util.spec_from_file_location('recovery',Path(__file__).resolve().parents[1]/'scripts/release-recovery.py')
        recovery=importlib.util.module_from_spec(spec);spec.loader.exec_module(recovery)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);live=root/'airnode';backup=root/('airnode-backup-'+'a'*32);units=root/'units';units.mkdir()
            live.mkdir();(live/'version').write_text('new');backup.mkdir();(backup/'version').write_text('old')
            (units/'airnode-api.service').write_text('new unit')
            record=root/'transaction.json';record.write_text(json.dumps({'backup':str(backup),'units':{'airnode-api.service':'old unit'}}))
            recovery.recover(record,live,units)
            self.assertEqual((live/'version').read_text(),'old')
            self.assertEqual((units/'airnode-api.service').read_text(),'old unit')
            self.assertFalse(record.exists())

class HardwarePreviewTests(unittest.TestCase):
    def test_no_fake_aircraft_or_mutating_host_actions(self):
        with tempfile.TemporaryDirectory() as temp:
            app=App(temp,local_preview=True,data=str(Path(temp)/'missing'))
            self.assertFalse(app.aircraft()['demo'])
            self.assertEqual(app.aircraft()['aircraft'],[])
            self.assertTrue(app.aircraft()['stale'])
            self.assertEqual(app.status()['aircraft'],0)
            self.assertTrue(app.status()['local_preview'])
            with self.assertRaises(APIError): app.broker({'op':'wifi-connect','settings':{}})
            with self.assertRaises(APIError): app.broker({'op':'release-action','action':'install'})
