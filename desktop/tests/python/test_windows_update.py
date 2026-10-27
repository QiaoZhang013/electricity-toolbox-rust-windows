"""Windows full-installer channel; no live releases, credentials or user data."""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.error
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT),str(ROOT/'desktop/python'),str(ROOT/'电力工具箱')]
from github_update import Cancelled, UpdateError
from windows_update import WindowsUpdater, WINDOWS_REPOSITORY, parse_windows_release

PAYLOAD=b'MZverified-windows-installer'
def metadata(version='0.1.22'):
    name=f'ElectricityToolbox_{version}_windows_x64_setup.exe'
    return dict(tag_name='v'+version,draft=False,prerelease=False,body='Windows 更新说明',
        html_url=f'https://github.com/{WINDOWS_REPOSITORY}/releases/tag/v{version}',
        assets=[dict(name=name,size=len(PAYLOAD),digest='sha256:'+hashlib.sha256(PAYLOAD).hexdigest(),
                     browser_download_url=f'https://github.com/{WINDOWS_REPOSITORY}/releases/download/v{version}/{name}')])

class Response(io.BytesIO):
    status=200
    def __init__(self,data,url='',headers=None):super().__init__(data);self.url=url;self.headers=headers or {}
    def geturl(self):return self.url

class WindowsChannelTests(unittest.TestCase):
    def test_channel_accepts_only_exact_windows_asset_from_our_repository(self):
        release=parse_windows_release(metadata(),'0.1.21')
        self.assertEqual(release.asset['name'],'ElectricityToolbox_0.1.22_windows_x64_setup.exe')
        self.assertIsNone(release.update_asset)
        for change in (dict(draft=True),dict(prerelease=True),dict(tag_name='v0.1.21')):
            data=metadata();data.update(change)
            self.assertIsNone(parse_windows_release(data,'0.1.21'))

    def test_invalid_asset_is_rejected_before_download(self):
        for field,value in [('name','bad.dmg'),('size',True),('size',0),('digest',''),
                            ('browser_download_url','https://github.com/evil/repo/releases/download/v0.1.22/setup.exe')]:
            data=metadata();data['assets'][0][field]=value
            with self.subTest(field=field,value=value),self.assertRaises(UpdateError):parse_windows_release(data,'0.1.21')
        data=metadata();data['assets']*=2
        with self.assertRaises(UpdateError):parse_windows_release(data,'0.1.21')

    def test_checks_actual_windows_channel_then_verifies_download(self):
        calls=[]
        def opener(request,timeout):
            calls.append(request.full_url)
            return Response(json.dumps(metadata()).encode() if request.full_url.endswith('/latest') else PAYLOAD)
        updater=WindowsUpdater('0.1.21',opener=opener)
        release=updater.check()
        self.assertEqual(calls[0],f'https://api.github.com/repos/{WINDOWS_REPOSITORY}/releases/latest')
        path=updater.download(release,threading.Event(),lambda _:None)
        self.addCleanup(lambda: __import__('shutil').rmtree(path.parent,ignore_errors=True))
        self.assertEqual(path.read_bytes(),PAYLOAD)
        self.assertTrue(path.name.endswith('.exe'))

    def test_rate_limit_fallback_reads_only_verified_windows_asset(self):
        data=metadata();asset=data['assets'][0];calls=[]
        base=f'https://github.com/{WINDOWS_REPOSITORY}/releases'
        def opener(request,timeout):
            calls.append((request.full_url,request.get_method()))
            if request.full_url.startswith('https://api.github.com/'):
                raise urllib.error.HTTPError(request.full_url,403,'rate limit',{},None)
            if request.full_url==base+'/latest':
                return Response(b'<div class="markdown-body">Windows notes</div>',data['html_url'])
            if request.full_url==base+'/expanded_assets/v0.1.22':
                html=f'<li><a href="/{WINDOWS_REPOSITORY}/releases/download/v0.1.22/{asset["name"]}">installer</a><clipboard-copy value="{asset["digest"]}"></clipboard-copy></li>'
                return Response(html.encode(),request.full_url)
            if request.full_url==asset['browser_download_url'] and request.get_method()=='HEAD':
                return Response(b'',request.full_url,{'Content-Length':str(len(PAYLOAD))})
            raise AssertionError(request.full_url)
        release=WindowsUpdater('0.1.21',opener=opener).check()
        self.assertEqual(release.asset,asset)
        self.assertTrue(all('apple' not in url for url,_ in calls))

    def test_corrupt_or_cancelled_download_leaves_no_installer(self):
        release=parse_windows_release(metadata(),'0.1.21')
        updater=WindowsUpdater('0.1.21',opener=lambda *a,**kw:Response(PAYLOAD[:-1]+b'!'))
        with self.assertRaisesRegex(UpdateError,'校验'):updater.download(release,threading.Event(),lambda _:None)
        cancel=threading.Event();cancel.set()
        with self.assertRaises(Cancelled):updater.download(release,cancel,lambda _:None)

    def test_source_launch_cannot_install_and_busy_service_cannot_be_reserved(self):
        updater=WindowsUpdater('0.1.21')
        with patch.dict(os.environ,{},clear=True),self.assertRaisesRegex(UpdateError,'安装'):updater.prepare_update()

    def test_abort_releases_only_our_maintenance_reservation(self):
        from unittest.mock import Mock
        client=Mock();updater=WindowsUpdater('0.1.21',client)
        with patch.dict(os.environ,{'TOOLBOX_INSTALLED':'1'}):updater.prepare_update()
        updater.abort_update()
        self.assertEqual([call.args[0] for call in client.call.call_args_list],['prepare_update','abort_update'])

    def test_previous_helper_failure_is_shown_once(self):
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'TOOLBOX_APP_HOME':directory}):
            path=Path(directory)/'state/windows-update.json';path.parent.mkdir()
            path.write_text(json.dumps(dict(state='failed',error='安装失败；已恢复旧程序')),encoding='utf-8')
            updater=WindowsUpdater('0.1.21')
            self.assertIn('已恢复旧程序',updater.take_install_error())
            self.assertIsNone(updater.take_install_error())

    def test_successful_update_cache_is_removed_without_touching_other_files(self):
        with tempfile.TemporaryDirectory() as home,tempfile.TemporaryDirectory(prefix='ElectricityToolboxWindowsUpdate-') as cache:
            root=Path(cache);version='0.1.22'
            (root/installer_name_for_test(version)).write_bytes(PAYLOAD)
            (root/'toolbox-update.exe').write_bytes(b'helper')
            (root/'plan.json').write_text(json.dumps(dict(app_home=home,version=version)),encoding='utf-8')
            state=Path(home)/'state/windows-update.json';state.parent.mkdir()
            state.write_text(json.dumps(dict(state='succeeded',version=version,cache=cache)),encoding='utf-8')
            with patch.dict(os.environ,{'TOOLBOX_APP_HOME':home}):WindowsUpdater('0.1.22').cleanup_completed_download()
            self.assertFalse(root.exists())
            with tempfile.TemporaryDirectory(prefix='ElectricityToolboxWindowsUpdate-') as foreign:
                candidate=Path(foreign)
                (candidate/'plan.json').write_text(json.dumps(dict(app_home=home,version=version)),encoding='utf-8')
                (candidate/'keep-user-file.txt').write_text('KEEP')
                state.write_text(json.dumps(dict(state='succeeded',version=version,cache=foreign)),encoding='utf-8')
                with patch.dict(os.environ,{'TOOLBOX_APP_HOME':home}):
                    self.assertFalse(WindowsUpdater('0.1.22').cleanup_completed_download())
                self.assertEqual((candidate/'keep-user-file.txt').read_text(),'KEEP')

def installer_name_for_test(version):
    return f'ElectricityToolbox_{version}_windows_x64_setup.exe'

class SharedVersionTests(unittest.TestCase):
    def test_invalid_host_version_uses_installed_metadata_then_unknown(self):
        import toolbox_version
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'TOOLBOX_APP_VERSION':'bad\nversion'}):
            root=Path(directory);state=root/'state/installed.json';state.parent.mkdir()
            state.write_text('{"version":"0.1.22"}')
            with patch.object(toolbox_version,'__file__',str(root/'app/toolbox_version.py')):
                self.assertEqual(toolbox_version.application_version(),'0.1.22')
                state.write_text('{"version":false}')
                self.assertEqual(toolbox_version.application_version(),'未知')

    def test_native_bridge_selects_windows_updater_and_preserves_mac_remote(self):
        from unittest.mock import Mock
        import native_bridge
        from remote_updater import RemoteUpdater
        with patch('native_bridge.sys.platform','win32'):
            self.assertIsInstance(native_bridge.create_updater(Mock()),WindowsUpdater)
        with patch('native_bridge.sys.platform','darwin'):
            self.assertIsInstance(native_bridge.create_updater(Mock()),RemoteUpdater)

    def test_installed_log_and_status_bar_use_host_version(self):
        import tkinter as tk
        from toolbox_log_console import LogConsole
        from toolbox.app import application_version
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'TOOLBOX_APP_VERSION':'0.1.22'}):
            root=tk.Tk();root.withdraw()
            try:
                console=LogConsole(root,module='验收',directory=Path(folder))
                console.begin()
                self.assertIn('版本：0.1.22',console.contents())
                self.assertEqual(application_version(),'版本 v0.1.22')
            finally:root.destroy()

if __name__=='__main__':unittest.main()
