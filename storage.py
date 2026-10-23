"""Resolve the shared music mount and check writes as the actual application user."""
import os
import tempfile
from pathlib import Path


class MusicStorage:
    def __init__(self, root=None):
        self.root = Path(root or os.environ.get('HUB_MUSIC_ROOT', '/music')).resolve()
        self.host_path = os.environ.get('HUB_MUSIC_HOST_PATH', './data/music')

    def resolve(self, value):
        if not isinstance(value, str) or not value.strip() or '\x00' in value or '\\' in value or '..' in value.split('/'):
            raise ValueError('请选择音乐挂载目录或其子目录')
        value = value.strip()
        # The public namespace is always /music, even in tests using another root.
        if value != '/music' and not value.startswith('/music/'):
            raise ValueError('路径须为 /music 或其子目录；宿主机路径请在 Compose 中映射')
        target = (self.root / value.removeprefix('/music').lstrip('/')).resolve()
        if not target.is_relative_to(self.root):
            raise ValueError('目录链接指向音乐挂载范围之外，请选择其他目录')
        return target

    def check(self, value, create=False):
        target = self.resolve(value)
        if create:
            target.mkdir(parents=True, exist_ok=True)
        if not target.is_dir():
            raise ValueError('目录不存在，请先在目录选择器中创建')
        try:
            with tempfile.TemporaryFile(dir=target, prefix='.music-hub-check-') as probe:
                probe.write(b'music-hub'); probe.flush()
        except OSError:
            raise ValueError('音乐目录不可写。请检查是否只读挂载，并授予容器 UID 1000 对此目录的读写权限') from None
        return target

    def browse(self, value):
        target = self.resolve(value)
        if not target.is_dir():
            raise ValueError('目录不存在')
        entries = []
        for child in sorted(target.iterdir(), key=lambda p: p.name.casefold()):
            if child.name.startswith('.'):
                continue
            resolved = child.resolve()
            if child.is_dir() and resolved.is_relative_to(self.root):
                entries.append({'name': child.name, 'path': '/music/' + child.relative_to(self.root).as_posix()})
        error = ''
        try:
            self.check(value)
        except ValueError as exc:
            error = str(exc)
        return {'path': value, 'directories': entries, 'writable': not error, 'error': error,
                'mapping': {'container': '/music', 'host': self.host_path}, 'uid': getattr(os, 'getuid', lambda: 1000)()}
