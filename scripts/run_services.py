"""Run the loopback-only engine and web gateway with one container lifecycle."""
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


def main():
    children = []
    stopping = False

    def stop(_signal=None, _frame=None):
        nonlocal stopping
        stopping = True
        for child in children:
            if child.poll() is None:
                try:
                    os.killpg(child.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        env = os.environ.copy()
        env['ENGINE_INTERNAL_TOKEN'] = Path(env['ENGINE_INTERNAL_TOKEN_FILE']).read_text().strip()
        engine = subprocess.Popen(
            ['music-dl', 'web', '--host', '127.0.0.1', '--port', '9981', '--no-browser'],
            cwd='/home/hub', env=env, start_new_session=True,
        )
        children.append(engine)
        deadline = time.monotonic() + 90
        while not stopping:
            if engine.poll() is not None:
                raise RuntimeError('Download engine exited during startup')
            try:
                with urllib.request.urlopen('http://127.0.0.1:9981/music/healthz', timeout=2):
                    break
            except OSError:
                if time.monotonic() >= deadline:
                    raise RuntimeError('Download engine startup timed out')
                time.sleep(0.5)
        if stopping:
            return 0
        children.append(subprocess.Popen(
            ['gunicorn', '--bind', '0.0.0.0:8000', '--workers', '1', '--threads', '16',
             '--timeout', '180', '--graceful-timeout', '20', 'app:app'],
            cwd='/app', start_new_session=True,
        ))
        print('Music Hub web and download engine ready', flush=True)
        while not stopping:
            if any(child.poll() is not None for child in children):
                raise RuntimeError('A Music Hub service exited; restarting container')
            time.sleep(0.5)
        return 0
    except Exception as exc:
        print(str(exc), file=sys.stderr, flush=True)
        return 1
    finally:
        stop()
        deadline = time.monotonic() + 25
        for child in children:
            try:
                child.wait(timeout=max(0.1, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()


if __name__ == '__main__':
    sys.exit(main())
