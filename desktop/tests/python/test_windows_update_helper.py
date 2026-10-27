"""Exercise the actual detached Rust helper with disposable tiny NSIS fixtures."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

ROOT=Path(__file__).resolve().parents[3]
SERVICE=Path(os.environ.get('TOOLBOX_SERVICE_BINARY',ROOT/'电力工具箱/bin/toolbox-service.exe'))
MAKENSIS=Path(os.environ.get('LOCALAPPDATA',''))/'tauri/NSIS/makensis.exe'

@unittest.skipUnless(os.name=='nt' and SERVICE.is_file() and MAKENSIS.is_file(),'Windows native helper and NSIS')
class WindowsHelperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixtures=tempfile.TemporaryDirectory(prefix='update-nsis-')
        folder=Path(cls.fixtures.name)
        cls.installers={}
        for name in ('good','fail','badapp'):
            fail=name=='fail'
            manifest=folder/(name+'.json');manifest.write_text(json.dumps({'version':'9.0.1'}))
            installer=folder/(name+'.exe')
            script=folder/(name+'.nsi')
            binary=SERVICE
            if name=='badapp':
                binary=folder/'not-a-program.exe';binary.write_bytes(b'MZinvalid')
            script.write_text('Unicode true\nRequestExecutionLevel user\nSilentInstall silent\nSetCompress off\n'
                f'OutFile "{installer}"\nSection\nSetOutPath "$INSTDIR"\n'
                f'File "/oname=electricity-toolbox.exe" "{binary}"\n'
                f'SetOutPath "$INSTDIR\\payload"\nFile "/oname=manifest.json" "{manifest}"\n'
                + ('SetErrorLevel 7\nQuit\n' if fail else 'SetErrorLevel 0\n')+'SectionEnd\n',encoding='utf-8-sig')
            result=subprocess.run([str(MAKENSIS),str(script)],capture_output=True,timeout=30,creationflags=subprocess.CREATE_NO_WINDOW)
            assert result.returncode==0,result.stdout.decode(errors='replace')+result.stderr.decode(errors='replace')
            cls.installers[name]=installer
    @classmethod
    def tearDownClass(cls):cls.fixtures.cleanup()

    def setUp(self):
        import shutil
        self.temp=tempfile.TemporaryDirectory(prefix='Windows 升级 空格 ')
        self.root=Path(self.temp.name);self.target=self.root/'安装 & 程序'
        self.target.mkdir();(self.target/'payload').mkdir()
        (self.target/'payload/manifest.json').write_text('{"version":"9.0.0"}')
        shutil.copy2(SERVICE,self.target/'electricity-toolbox.exe')
        self.home=self.root/'用户 数据';self.home.mkdir();(self.home/'keep.txt').write_text('KEEP-DATA')
        self.cache=self.root/'cache';self.cache.mkdir()
        self.processes=[];self.helper=None
    def tearDown(self):
        for child in self.processes:
            if child.poll() is None:child.stdin.close()
            child.wait(timeout=8)
            for stream in (child.stdin,child.stdout,child.stderr):
                if stream and not stream.closed:stream.close()
        if self.helper and self.helper.poll() is None:
            (self.cache/'decision.json').write_text(json.dumps({'token':'test-owned','action':'abort'}))
            self.helper.wait(timeout=8)
        deadline=time.monotonic()+5
        while True:
            try:self.temp.cleanup();break
            except PermissionError:
                if time.monotonic()>=deadline:raise
                time.sleep(.02)
    def children(self):
        for path in (self.target/'electricity-toolbox.exe',SERVICE,SERVICE):
            child=subprocess.Popen([str(path)],cwd=self.root,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW)
            self.assertIn(b'service-ready',child.stdout.readline())
            self.processes.append(child)
        return [dict(pid=p.pid,path=str(path.resolve())) for p,path in zip(self.processes,(self.target/'electricity-toolbox.exe',SERVICE,SERVICE))]
    def status(self):
        path=self.cache/'status.json'
        try:return json.loads(path.read_text(encoding='utf-8'))
        except (OSError,ValueError):return {}
    def launch(self,kind='good',**changes):
        import shutil
        installer=self.cache/'installer.exe';shutil.copy2(self.installers[kind],installer)
        plan=dict(schema=1,installer=str(installer),sha256=hashlib.sha256(installer.read_bytes()).hexdigest(),size=installer.stat().st_size,
                  version='9.0.1',target_dir=str(self.target),app_home=str(self.home),processes=self.children(),token='test-owned',wait_timeout_ms=2000)
        plan.update(changes);(self.cache/'plan.json').write_text(json.dumps(plan),encoding='utf-8')
        self.helper=subprocess.Popen([str(SERVICE),'--windows-update-helper',str(self.cache/'plan.json')],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
        deadline=time.monotonic()+5
        while not self.status() and self.helper.poll() is None and time.monotonic()<deadline:time.sleep(.02)
        self.assertEqual(self.status().get('state'),'ready',self.status())
        return installer
    def commit(self):
        (self.cache/'decision.json').write_text(json.dumps({'token':'test-owned','action':'commit'}))
        for p in self.processes:p.stdin.close()
        self.helper.wait(timeout=15)

    def test_invalid_plan_is_rejected_instead_of_serving_normal_protocol(self):
        plan=self.cache/'plan.json';plan.write_text('{}')
        result=subprocess.run([str(SERVICE),'--windows-update-helper',str(plan)],input=b'',capture_output=True,timeout=5,creationflags=subprocess.CREATE_NO_WINDOW)
        self.assertNotEqual(result.returncode,0)

    def test_real_nsis_install_waits_for_owned_processes_and_relaunches(self):
        self.launch()
        (self.cache/'decision.json').write_text(json.dumps({'token':'test-owned','action':'commit'}))
        time.sleep(.15)
        self.assertEqual(json.loads((self.target/'payload/manifest.json').read_text())['version'],'9.0.0')
        for p in self.processes:p.stdin.close()
        self.helper.wait(timeout=15)
        self.assertEqual(self.status()['state'],'succeeded',self.status())
        self.assertEqual(json.loads((self.target/'payload/manifest.json').read_text())['version'],'9.0.1')
        self.assertEqual((self.home/'keep.txt').read_text(),'KEEP-DATA')
        self.assertGreater(self.status()['relaunch_pid'],0)

    def test_partial_install_failure_restores_old_program_and_data(self):
        self.launch('fail');self.commit()
        self.assertEqual(self.status()['state'],'failed',self.status())
        self.assertEqual(json.loads((self.target/'payload/manifest.json').read_text())['version'],'9.0.0')
        self.assertEqual((self.home/'keep.txt').read_text(),'KEEP-DATA')

    def test_changed_installer_cannot_replace_program(self):
        installer=self.launch();installer.write_bytes(b'MZchanged')
        self.commit()
        self.assertEqual(self.status()['state'],'failed')
        self.assertEqual(json.loads((self.target/'payload/manifest.json').read_text())['version'],'9.0.0')

    def test_unlaunchable_new_program_rolls_back_before_discarding_old_version(self):
        self.launch('badapp');self.commit()
        self.assertEqual(self.status()['state'],'failed',self.status())
        self.assertEqual(json.loads((self.target/'payload/manifest.json').read_text())['version'],'9.0.0')

    def test_abort_does_not_stop_processes_or_install(self):
        self.launch()
        (self.cache/'decision.json').write_text(json.dumps({'token':'test-owned','action':'abort'}))
        self.helper.wait(timeout=8)
        self.assertEqual(self.status()['state'],'aborted')
        self.assertTrue(all(p.poll() is None for p in self.processes))

    def test_timeout_never_replaces_a_running_program(self):
        self.launch(wait_timeout_ms=200)
        (self.cache/'decision.json').write_text(json.dumps({'token':'test-owned','action':'commit'}))
        self.helper.wait(timeout=8)
        self.assertEqual(self.status()['state'],'failed')
        self.assertEqual(json.loads((self.target/'payload/manifest.json').read_text())['version'],'9.0.0')
        self.assertTrue(all(p.poll() is None for p in self.processes))
