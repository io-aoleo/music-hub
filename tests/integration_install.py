"""Run ONLY against an isolated, loopback-bound fresh Compose test project.

docker exec -i music-hub-freshcheck-hub-1 python - --fresh < tests/integration_install.py
Use --resume after restarting that test project. This fixture account is not for production.
"""
import argparse
import json
import time
import requests
from pathlib import Path

parser=argparse.ArgumentParser();parser.add_argument('--fresh',action='store_true');parser.add_argument('--resume',action='store_true');args=parser.parse_args()
assert args.fresh != args.resume,'Choose --fresh or --resume'
base='http://127.0.0.1:8000';client=requests.Session();client.trust_env=False
state=client.get(base+'/api/auth/status').json()
username='installation-check';password='installation-fixture-password-123'
def post(path,body):
    state=client.get(base+'/api/auth/status').json()
    response=client.post(base+path,json=body,headers={'X-CSRF-Token':state['csrf']},timeout=170)
    assert response.ok,(path,response.status_code,response.text[:200])
    return response.json()
if args.fresh:
    assert not state['configured'],'Not a fresh test install; refusing to modify an existing administrator'
    assert client.get(base+'/',allow_redirects=False).headers['Location']=='/setup'
    post('/api/auth/setup',{'username':username,'password':password,'confirmation':password})
else:
    post('/api/auth/login',{'username':username,'password':password})
mapping=client.get(base+'/api/storage').json();assert mapping['writable'] and mapping['uid']==1000,mapping
print('shared_mount',json.dumps(mapping['mapping'],ensure_ascii=False))
if args.fresh:
    post('/api/storage',{'path':'/music/check-downloads'})
    post('/api/preferences',{'downloadDir':'/music/check-downloads','tokens':{}})
    response=client.get(base+'/api/search',params={'q':'晴天','source':'netease'},timeout=170)
    response.raise_for_status();songs=response.json()['songs'];assert len(songs)>=2
    batch=post('/api/downloads',{'songs':songs[:2]});assert batch['added']==2
    for _ in range(100):
        downloads=client.get(base+'/api/downloads').json()
        if not downloads.get('counts',{}).get('queued') and not downloads.get('counts',{}).get('running'):break
        time.sleep(1)
    print('real_platform_downloads',json.dumps(downloads['counts'],ensure_ascii=False))
    assert not downloads['counts'].get('queued') and not downloads['counts'].get('running'), 'Queue did not finish'
    assert downloads['counts'].get('done',0)>=1, 'No downloadable track found; check platform availability'
    assert len(downloads['downloads'])==2, 'Batch must retain successful and failed records'
else:
    downloads=client.get(base+'/api/downloads').json();assert downloads['counts'].get('done',0)>=1
    assert len(downloads['downloads'])==2
    assert client.get(base+'/api/preferences').json()['downloadDir']=='/music/check-downloads'
    print('persistent_account_settings_download_history',True)
assert client.get(base+'/healthz').status_code==200
snapshot=Path('/data/tasks/install-check-counts.json')
if snapshot.exists(): assert json.loads(snapshot.read_text())==downloads['counts'],'Download counts changed across restart'
else: snapshot.write_text(json.dumps(downloads['counts']))
print('PASS fresh Compose integration' if args.fresh else 'PASS restart persistence integration')
