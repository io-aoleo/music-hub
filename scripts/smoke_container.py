"""Exercise an actual image with disposable volumes; no real NAS data is mounted."""
import json
import subprocess
import sys
import time
import uuid

IMAGE = sys.argv[1] if len(sys.argv) > 1 else 'music-hub:smoke'
NAME = 'music-hub-smoke-' + uuid.uuid4().hex[:10]


def docker(*args):
    return subprocess.check_output(['docker', *args], text=True).strip()


def inside(code):
    return docker('exec', NAME, 'python', '-c', code)


def ready():
    for _ in range(90):
        result = subprocess.run(
            ['docker', 'exec', NAME, 'python', '-c',
             "import json,urllib.request; assert json.load(urllib.request.urlopen('http://127.0.0.1:8000/healthz',timeout=2))['engine']"],
            capture_output=True,
        )
        if result.returncode == 0:
            return
        time.sleep(1)
    raise RuntimeError('Container failed to become ready')


try:
    docker('run', '-d', '--name', NAME,
           '-v', NAME + '-tasks:/data/tasks', '-v', NAME + '-engine:/data/engine',
           '-v', NAME + '-config:/shared', '-v', NAME + '-music:/music', IMAGE)
    ready()
    inside("""
import requests, secrets, pathlib, os
s=requests.Session(); base='http://127.0.0.1:8000'
d=s.get(base+'/api/auth/status').json()
assert d['configured'] is False and d['auth_required'] is True
assert s.get(base+'/',allow_redirects=False).headers['Location'].endswith('/setup')
password=secrets.token_urlsafe(24)
r=s.post(base+'/api/auth/setup',json={'username':'smoketest','password':password,'confirmation':password},headers={'X-CSRF-Token':d['csrf']})
assert r.ok, r.status_code
assert s.get(base+'/api/auth/status').json()['authenticated'] is True
assert s.get(base+'/api/preferences').ok
r=s.get(base+'/api/storage',params={'path':'/music'})
assert r.ok and r.json()['writable'] is True
pathlib.Path('/music/persistence-check').write_text('retained')
assert pathlib.Path('/shared/engine-token').stat().st_uid == 1000
assert pathlib.Path('/data/engine/settings.db').stat().st_uid == 1000
""")
    docker('restart', '-t', '35', NAME)
    ready()
    inside("""
import requests,pathlib
d=requests.get('http://127.0.0.1:8000/api/auth/status').json()
assert d['configured'] is True and d['authenticated'] is False
assert pathlib.Path('/music/persistence-check').read_text()=='retained'
""")
    # An engine failure must terminate the container, so restart policies can recover it.
    inside("""
import pathlib,os,signal
for p in pathlib.Path('/proc').iterdir():
 if p.name.isdigit():
  try:
   if (p/'comm').read_text().strip()=='music-dl': os.kill(int(p.name),signal.SIGTERM)
  except (FileNotFoundError,ProcessLookupError): pass
""")
    for _ in range(40):
        if docker('inspect', '-f', '{{.State.Running}}', NAME) == 'false':
            break
        time.sleep(1)
    assert docker('inspect', '-f', '{{.State.Running}}', NAME) == 'false'
    assert docker('inspect', '-f', '{{.State.ExitCode}}', NAME) == '1'
    docker('start', NAME)
    ready()
    docker('stop', '-t', '35', NAME)
    assert docker('inspect', '-f', '{{.State.ExitCode}}', NAME) == '0'
    print('PASS: first-run account, writable music, restart persistence, engine failure, graceful stop')
except Exception:
    subprocess.run(['docker', 'logs', '--tail', '100', NAME])
    raise
finally:
    subprocess.run(['docker', 'rm', '-f', NAME], stdout=subprocess.DEVNULL)
    for suffix in ('tasks', 'engine', 'config', 'music'):
        subprocess.run(['docker', 'volume', 'rm', NAME + '-' + suffix], stdout=subprocess.DEVNULL)
