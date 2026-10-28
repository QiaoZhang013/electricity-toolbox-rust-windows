"""Windows full-installer channel; reuse the existing verified download transport."""
from __future__ import annotations

import os
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

from github_update import GitHubUpdater, Release, UpdateError, version_parts

WINDOWS_REPOSITORY = "QiaoZhang013/electricity-toolbox-rust-windows"


def installer_name(tag):
    return f"ElectricityToolbox_{tag.removeprefix('v')}_windows_x64_setup.exe"


def parse_windows_release(data, current):
    try:
        tag = data['tag_name']
        latest = version_parts(tag)
        if data['draft'] or data['prerelease'] or latest <= version_parts(current):
            return None
        base = f'https://github.com/{WINDOWS_REPOSITORY}/releases'
        if data['html_url'] != f'{base}/tag/{tag}':
            raise UpdateError('Windows 版本发布页面无效')
        name = installer_name(tag)
        assets = [asset for asset in data['assets'] if asset['name'] == name]
        if len(assets) != 1:
            raise UpdateError('此版本缺少唯一的 Windows x64 安装包')
        asset = assets[0]
        if (type(asset['size']) is not int or not 0 < asset['size'] <= 2 * 1024**3
                or not isinstance(asset['digest'], str)
                or not re.fullmatch(r'sha256:[a-fA-F0-9]{64}', asset['digest'])
                or asset['browser_download_url'] != f'{base}/download/{tag}/{name}'):
            raise UpdateError('Windows 安装包链接、大小或 SHA-256 摘要无效')
        return Release(tag, str(data.get('body') or '此版本没有提供更新说明。')[:100_000],
                       data['html_url'], dict(asset))
    except (KeyError, TypeError, AttributeError) as exc:
        raise UpdateError('Windows 版本信息无效') from exc


class WindowsUpdater(GitHubUpdater):
    platform_label = 'Windows x64'

    def __init__(self, current, client=None, opener=None):
        super().__init__(current, repository=WINDOWS_REPOSITORY, opener=opener)
        self.client = client
        self._reserved = False
        self._helper = None
        self._plan = None

    def check(self):
        return self.check_release()

    def parse_data(self, data):
        return parse_windows_release(data, self.current)

    def primary_asset_name(self, tag):
        return installer_name(tag)

    def release_asset_names(self, tag):
        return {self.primary_asset_name(tag)}

    def download(self, release, cancel, progress):
        directory = Path(tempfile.mkdtemp(prefix='ElectricityToolboxWindowsUpdate-'))
        path = directory / installer_name(release.version)
        try:
            checked = parse_windows_release(dict(tag_name=release.version, draft=False, prerelease=False,
                html_url=release.page, body=release.notes, assets=[release.asset]), self.current)
            if checked is None:
                raise UpdateError('更新版本不高于当前版本')
            return self.remember_download(release, self.download_asset(checked.asset, path, cancel, progress))
        except BaseException:
            shutil.rmtree(directory, ignore_errors=True)
            raise

    def prepare_update(self):
        if os.environ.get('TOOLBOX_INSTALLED') != '1' or self.client is None:
            raise UpdateError('请使用完整安装后的 Windows 桌面版执行自动安装')
        result = self.client.call('prepare_update')
        self._reserved = True
        return result

    @staticmethod
    def _atomic_json(path, value):
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
        temporary.replace(path)

    def _status(self):
        if self._plan is None:
            return {}
        try:
            return json.loads((self._plan.parent/'status.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return {}

    def prepare_install(self, release, path):
        if not self._reserved or self.downloaded is None or self.downloaded[:2] != (release.version, Path(path)):
            raise UpdateError('安装包未经过本次更新校验，请重新下载')
        try:
            root = Path(os.environ['TOOLBOX_INSTALL_ROOT']).resolve(strict=True)
            home = Path(os.environ['TOOLBOX_APP_HOME']).resolve(strict=True)
            host = int(os.environ['TOOLBOX_HOST_PID'])
            if not (root/'electricity-toolbox.exe').is_file() or home.is_relative_to(root) or host <= 0:
                raise ValueError('invalid installation')
        except (KeyError, OSError, ValueError) as exc:
            raise UpdateError('Windows 安装路径或宿主进程信息无效，请重新打开安装版') from exc
        with Path(path).open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        if digest != self.downloaded[2]:
            raise UpdateError('下载后的安装包已变化，请重新下载')
        ping = self.client.call('ping')
        if ping.get('engine') != 'rust' or ping.get('protocol') != 3:
            raise UpdateError('界面与 Rust 更新后台不匹配，请重新安装完整版本')
        service = Path(__file__).resolve().parents[2]/'电力工具箱/bin/toolbox-service.exe'
        helper = Path(path).parent/'toolbox-update.exe'
        shutil.copy2(service, helper)
        token = str(uuid.uuid4())
        self._plan = Path(path).parent/'plan.json'
        self._token = token
        self._atomic_json(self._plan, dict(schema=1, installer=str(Path(path).resolve()), sha256=digest,
            size=Path(path).stat().st_size, version=release.version.removeprefix('v'), target_dir=str(root), app_home=str(home),
            token=token, processes=[dict(pid=host,path=str(root/'electricity-toolbox.exe')),
                dict(pid=os.getpid(),path=str(Path(sys.executable).resolve())),dict(pid=ping['pid'],path=str(service))]))
        with (self._plan.parent/'helper.log').open('wb') as log:
            self._helper = subprocess.Popen([str(helper),'--windows-update-helper',str(self._plan)],
                stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=log,
                creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP)
        deadline = time.monotonic()+10
        while time.monotonic()<deadline:
            if self._status().get('state') == 'ready' and self._helper.poll() is None:
                return True
            if self._helper.poll() is not None:
                detail = (self._plan.parent/'helper.log').read_text(encoding='utf-8',errors='replace')[-1200:]
                raise UpdateError('Windows 安装助手未完成准备：'+detail)
            time.sleep(.02)
        raise UpdateError('Windows 安装助手准备超时，未替换程序')

    def commit_install(self):
        if self._plan is None or self._helper is None or self._helper.poll() is not None or self._status().get('state') != 'ready':
            raise UpdateError('Windows 自动安装尚未准备完成')
        self._atomic_json(self._plan.parent/'decision.json',dict(action='commit',token=self._token))
        return True

    def abort_update(self):
        if self._helper is not None and self._helper.poll() is None:
            self._atomic_json(self._plan.parent/'decision.json',dict(action='abort',token=self._token))
            try:
                self._helper.wait(timeout=5)
            except subprocess.TimeoutExpired as exc:
                raise UpdateError('安装助手尚未确认取消，请稍后重试') from exc
        if self._reserved:
            self.client.call('abort_update')
            self._reserved = False
        self._helper = None
        self._plan = None
        if self.downloaded is not None:
            shutil.rmtree(self.downloaded[1].parent, ignore_errors=True)
            self.downloaded = None

    def take_install_error(self):
        home = os.environ.get('TOOLBOX_APP_HOME')
        if not home:
            return None
        path = Path(home)/'state/windows-update.json'
        try:
            status = json.loads(path.read_text(encoding='utf-8'))
            if status.get('state') != 'failed' or status.get('notified'):
                return None
            status['notified'] = True
            self._atomic_json(path, status)
            return str(status.get('error') or '上次 Windows 更新未完成，请重试。')
        except (OSError, ValueError, TypeError):
            return None

    def cleanup_completed_download(self):
        """Run off the Tk thread; delete only an owned successful update cache."""
        home = os.environ.get('TOOLBOX_APP_HOME')
        if not home:
            return False
        report = Path(home)/'state/windows-update.json'
        try:
            for _ in range(50):
                status = json.loads(report.read_text(encoding='utf-8'))
                if status.get('state') != 'installing':
                    break
                time.sleep(.2)
            if status.get('state') != 'succeeded':
                return False
            cache = Path(str(status['cache']).removeprefix('\\\\?\\')).resolve()
            if cache.parent != Path(tempfile.gettempdir()).resolve() or not cache.name.startswith('ElectricityToolboxWindowsUpdate-'):
                return False
            if not cache.exists():
                return True
            if cache.is_symlink() or getattr(cache.lstat(),'st_file_attributes',0) & 0x400:
                return False
            plan = json.loads((cache/'plan.json').read_text(encoding='utf-8'))
            if Path(plan['app_home']).resolve() != Path(home).resolve() or plan['version'] != status['version']:
                return False
            names = {installer_name(status['version']), 'toolbox-update.exe', 'helper.log', 'plan.json',
                     'decision.json', 'status.json', 'uninstall-registry.reg', 'plan.tmp', 'decision.tmp', 'status.tmp'}
            children = list(cache.iterdir())
            if any(p.name not in names or not p.is_file() or p.is_symlink()
                   or getattr(p.lstat(),'st_file_attributes',0) & 0x400 for p in children):
                return False
            # Windows denies deletion while the helper's image is still running.
            for _ in range(50):
                try:
                    (cache/'toolbox-update.exe').unlink(missing_ok=True)
                    break
                except PermissionError:
                    time.sleep(.1)
            else:
                return False
            for path in children:
                path.unlink(missing_ok=True)
            cache.rmdir()
            return True
        except (OSError, ValueError, KeyError, TypeError):
            return False
