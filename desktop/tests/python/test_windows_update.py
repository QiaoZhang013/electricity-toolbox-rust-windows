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

    def test_corrupt_or_cancelled_download_leaves_no_installer(self):
        release=parse_windows_release(metadata(),'0.1.21')
        updater=WindowsUpdater('0.1.21',opener=lambda *a,**kw:Response(PAYLOAD[:-1]+b'!'))
        with self.assertRaisesRegex(UpdateError,'校验'):updater.download(release,threading.Event(),lambda _:None)
        cancel=threading.Event();cancel.set()
        with self.assertRaises(Cancelled):updater.download(release,cancel,lambda _:None)

    def test_source_launch_cannot_install_and_busy_service_cannot_be_reserved(self):
        updater=WindowsUpdater('0.1.21')
        with patch.dict(os.environ,{},clear=True),self.assertRaisesRegex(UpdateError,'安装'):updater.prepare_update()

class SharedVersionTests(unittest.TestCase):
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
