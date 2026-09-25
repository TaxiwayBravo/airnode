import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from airnode import aggregators as ag
from airnode.aggregator_control import Manager, upstream_connected
from airnode.server import App
import test_airnode

UID = "8fd02af1-9f1d-4f28-bd10-4e2bd409b4cc"
KEY = "0123456789abcdef"  # synthetic fixture; not a real provider key

class AggregatorSchemaTests(unittest.TestCase):
    def test_all_five_defaults_off(self):
        self.assertEqual(len(ag.PROVIDERS), 5)
        self.assertFalse(ag.public_settings('adsblol',None)['enabled'])

    def test_stable_generated_identity_per_provider(self):
        saved=ag.updated({}, {'provider':'adsblol','enabled':False})
        self.assertTrue(saved['adsblol']['credential'])
        again=ag.updated(saved, {'provider':'adsblol','enabled':True,'consent':True})
        self.assertEqual(saved['adsblol']['credential'],again['adsblol']['credential'])
        again=ag.updated(again, {'provider':'airplaneslive','enabled':False})
        self.assertNotEqual(again['adsblol']['credential'],again['airplaneslive']['credential'])

    def test_enable_requires_explicit_consent(self):
        for consent in [None, False, 'true', 1]:
            with self.assertRaises(ValueError):
                ag.updated({}, {'provider':'adsblol','enabled':True,'consent':consent})

    def test_unknown_provider_and_fields(self):
        for key in ['../piaware','adsblol;reboot','unknown',None]:
            with self.assertRaises(ValueError): ag.updated({}, {'provider':key,'enabled':False})
        with self.assertRaises(ValueError): ag.updated({}, {'provider':'adsblol','enabled':False,'command':'whoami'})

    def test_key_validation_and_preservation(self):
        for token in ['bad',KEY+'\nreboot','x'*16, '";id', '']:
            with self.assertRaises(ValueError): ag.updated({}, {'provider':'flightradar24','credential':token,'enabled':True,'consent':True})
        old=ag.updated({}, {'provider':'flightradar24','credential':KEY,'enabled':False})
        saved=ag.updated(old, {'provider':'flightradar24','credential':'','enabled':True,'consent':True})
        self.assertEqual(saved['flightradar24']['credential'],KEY)
        self.assertNotIn(KEY,json.dumps(ag.public_settings('flightradar24',saved['flightradar24'])))

    def test_identifier_validation(self):
        for token in ['--net-connector=evil',UID+',host', '00000000-0000-0000-0000-000000000000']:
            with self.assertRaises(ValueError): ag.updated({}, {'provider':'adsblol','credential':token,'enabled':False})

    def test_relay_has_no_radio_or_public_listener(self):
        for key in ['adsblol','airplaneslive','adsbexchange']:
            args=ag.relay_args(key,{'enabled':True,'credential':UID})
            self.assertIn('--net-only',args)
            self.assertIn('--net-connector=127.0.0.1,30005,beast_in',args)
            self.assertIn('--net-bo-port=0',args)
            self.assertFalse(any('device-type' in a for a in args))
            self.assertIn('uuid='+UID,' '.join(args))
        with self.assertRaises(ValueError): ag.relay_args('adsblol',{'enabled':False,'credential':UID})

    def test_native_config_keeps_receiver_local(self):
        fa=ag.native_config('flightaware',{'enabled':True,'credential':UID},'receiver-type rtlsdr\n# custom\nuse-gpsd no\n')
        self.assertIn('receiver-type other',fa)
        self.assertNotIn('receiver-type rtlsdr',fa)
        self.assertIn('use-gpsd no',fa)
        self.assertIn('allow-auto-updates no',fa)
        fr=ag.native_config('flightradar24',{'enabled':True,'credential':KEY},'receiver="dvbt"\n')
        self.assertIn('receiver="beast-tcp"',fr)
        self.assertIn('bind-interface="127.0.0.1"',fr)
        self.assertIn('bs="no"',fr)
        self.assertNotIn('dvbt',fr)

    def test_redacts_credentials_and_uuid(self):
        text=ag.redact('key='+KEY+' uuid='+UID,{'flightradar24':{'enabled':True,'credential':KEY}})
        self.assertNotIn(KEY,text)
        self.assertNotIn(UID,text)

    def test_socket_status_not_other_process_or_local_input(self):
        line='0 0 192.168.1.20:48001 1.2.3.4:30004 users:(("readsb",pid=123,fd=9))'
        self.assertTrue(upstream_connected(line,'123',{30004}))
        self.assertFalse(upstream_connected(line,'12',{30004}))
        self.assertFalse(upstream_connected(line.replace(':30004',':30005'),'123',{30004}))
        self.assertFalse(upstream_connected(line,'0',{30004}))

class AggregatorControlTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.command=Mock(return_value='')
        self.manager=Manager(self.command,self.root/'airnode',self.root)

    def test_missing_client_enable_no_writes(self):
        with patch.object(self.manager,'available',return_value=False):
            with self.assertRaises(ValueError): self.manager.configure({'provider':'flightradar24','credential':KEY,'enabled':True,'consent':True})
        self.assertFalse(self.manager.path.exists())
        self.assertFalse((self.root/'fr24feed.ini').exists())

    def test_save_disabled_key_no_service_mutation(self):
        with patch.object(self.manager,'available',return_value=False):
            self.manager.configure({'provider':'flightradar24','credential':KEY,'enabled':False})
        self.assertEqual(ag.load(self.manager.path)['flightradar24']['credential'],KEY)
        self.assertTrue(all(call.args[0][1]=='show' for call in self.command.call_args_list))

    def test_disabled_cannot_restart(self):
        with self.assertRaises(ValueError): self.manager.operate('adsblol','restart')
        self.command.assert_not_called()

    def test_native_config_enable_and_disable(self):
        target=self.root/'fr24feed.ini'
        target.write_text('receiver="dvbt"\n')
        with patch.object(self.manager,'available',return_value=True):
            self.manager.configure({'provider':'flightradar24','credential':KEY,'enabled':True,'consent':True})
            self.assertIn('beast-tcp',target.read_text())
            self.assertEqual(Path(str(target)+'.airnode-backup').read_text(),'receiver="dvbt"\n')
            self.manager.configure({'provider':'flightradar24','enabled':False})
        self.assertFalse(ag.load(self.manager.path)['flightradar24']['enabled'])
        self.command.assert_any_call(['systemctl','disable','--now','fr24feed.service'])

    def test_native_failure_restores_previous_file_and_hides_key(self):
        target=self.root/'fr24feed.ini';target.write_text('original\n')
        def command(args,**kwargs):
            if args[:2]==['systemctl','start']: raise ValueError('credential='+KEY)
            return ''
        self.manager.command=command
        with patch.object(self.manager,'available',return_value=True), patch('airnode.aggregator_control.os.chown',create=True):
            with self.assertRaises(ValueError) as error:
                self.manager.configure({'provider':'flightradar24','credential':KEY,'enabled':True,'consent':True})
        self.assertNotIn(KEY,str(error.exception))
        self.assertEqual(target.read_text(),'original\n')
        self.assertFalse(self.manager.path.exists())

    def test_status_not_claiming_provider_acceptance(self):
        self.command.return_value='LoadState=loaded\nActiveState=active\nMainPID=123\n'
        ag.save(self.manager.path,{'flightradar24':{'enabled':True,'credential':KEY}})
        with patch.object(self.manager,'available',return_value=True):
            result=self.manager.status()
        item=next(p for p in result['providers'] if p['id']=='flightradar24')
        self.assertEqual(item['state'],'Running · unverified')
        self.assertNotIn(KEY,json.dumps(result))

class AggregatorAPITests(test_airnode.APITests):
    # Inherits API security regression checks with its own isolated server/owner.
    def test_catalog_requires_auth(self):
        self.assertEqual(self.request('GET','/api/aggregators')[0],401)

    def test_wifi_and_release_api_security(self):
        for path in ('/api/wifi','/api/releases'):
            self.assertEqual(self.request('GET',path)[0],401)
            self.assertEqual(self.request('GET',path,headers=self.auth_headers())[0],200)
        wifi = {'ssid':'Home','password':'private-pass','country':'GB'}
        self.assertEqual(self.request('POST','/api/wifi/connect',wifi,{'Cookie':self.cookie})[0],403)
        code,_,result=self.request('POST','/api/wifi/connect',wifi,self.auth_headers())
        self.assertEqual(code,200);self.assertNotIn('private-pass',json.dumps(result))
        self.assertEqual(self.request('POST','/api/releases/action',{'action':'install'},self.auth_headers())[0],403)
        self.assertEqual(self.request('POST','/api/releases/action',{'action':'channel','channel':'arbitrary'},self.auth_headers())[0],400)

    def test_software_actions_auth_csrf_and_demo(self):
        body = {'provider':'flightaware','action':'install'}
        self.assertEqual(self.request('POST','/api/aggregators/action',body)[0],401)
        self.assertEqual(self.request('POST','/api/aggregators/action',body,{'Cookie':self.cookie})[0],403)
        with patch('airnode.maintenance.operate') as real_install:
            self.assertEqual(self.request('POST','/api/aggregators/action',body,self.auth_headers())[0],200)
            self.assertEqual(self.request('POST','/api/aggregators/action',{'provider':'flightaware','action':'auto-on'},self.auth_headers())[0],200)
        real_install.assert_not_called()
        _, _, data = self.request('GET','/api/aggregators',headers=self.auth_headers())
        provider = next(p for p in data['providers'] if p['id']=='flightaware')
        self.assertTrue(provider['software']['automatic'])
        self.assertTrue(provider['installed'])
        self.assertEqual(self.request('POST','/api/aggregators/action',{'provider':'../ssh','action':'install'},self.auth_headers())[0],400)

    def test_aggregator_writes_require_csrf(self):
        self.assertEqual(self.request('POST','/api/aggregators/config',{'provider':'adsblol','enabled':False},{'Cookie':self.cookie})[0],403)

    def test_roundtrip_redacted_after_reload(self):
        code,_,_=self.request('POST','/api/aggregators/config',{'provider':'flightradar24','credential':KEY,'enabled':True,'consent':True},self.auth_headers())
        self.assertEqual(code,200)
        code,_,result=self.request('GET','/api/aggregators',headers=self.auth_headers())
        self.assertEqual(code,200)
        self.assertNotIn(KEY,json.dumps(result))
        app=App(self.temp.name,demo=True)
        item=next(p for p in app.broker({'op':'aggregators'})['providers'] if p['id']=='flightradar24')
        self.assertTrue(item['enabled']);self.assertTrue(item['credential_set']);self.assertTrue(item['demo'])
        self.assertEqual(self.request('POST','/api/aggregators/config',{'provider':'flightradar24','enabled':False},self.auth_headers())[0],200)

    def test_enable_without_consent_rejected(self):
        self.assertEqual(self.request('POST','/api/aggregators/config',{'provider':'adsblol','enabled':True},self.auth_headers())[0],400)
