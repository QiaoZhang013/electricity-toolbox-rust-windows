"""Windows full-installer channel; reuse the existing verified download transport."""
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import tempfile

from github_update import GitHubUpdater, Release, UpdateError, version_parts

WINDOWS_REPOSITORY = "Qiaozhang13/electricity-toolbox-rust-windows"


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
        return self.client.call('prepare_update')
