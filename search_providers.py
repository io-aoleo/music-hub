"""Paginated provider adapters; download resolution still belongs to the engine.

Field mappings follow guohuiyuan/music-lib, revision 28e1080ba416 (AGPL-3.0),
the dependency pinned in vendor/go-music-dl/go.mod. No account entitlement is bypassed.
"""
import html
import json
import math
import re
import time
import requests

SOURCES = ('netease', 'qq', 'kuwo', 'kugou', 'migu')


class SearchUnavailable(Exception):
    pass


def number(value, default=0):
    try:
        return max(0, int(value))
    except (ValueError, TypeError):
        return default


def text(value):
    return html.unescape(re.sub(r'<[^>]+>', '', str(value or '')))


def song(source, identity, name, artist, album='', duration=0, cover='', extra=None):
    return dict(source=source, id=str(identity), name=text(name), artist=text(artist),
                album=text(album), duration=number(duration), cover=str(cover or ''),
                extra=json.dumps({k:str(v or '') for k,v in (extra or {}).items()}, ensure_ascii=False))


class ProviderSearch:
    def __init__(self, cookies):
        self.cookies = cookies

    def get(self, url, params, source, referer):
        headers = {'User-Agent':'Mozilla/5.0', 'Referer':referer,
                   'Cookie':self.cookies().get(source, ''), 'Accept':'application/json'}
        try:
            with requests.Session() as client:
                response = client.get(url, params=params, headers=headers, timeout=(5,25))
                response.raise_for_status()
                data = response.json()
            if not isinstance(data, dict):
                raise ValueError('invalid provider response')
            return data
        except (requests.RequestException, ValueError):
            raise SearchUnavailable('音乐平台暂时无法搜索，请稍后重试或更换来源') from None

    def search(self, query, source, page, page_size):
        songs, total, raw_count = getattr(self, source)(query, page, page_size)
        songs = [s for s in songs if s['id'] and s['id'] != 'None']
        total = number(total) if total is not None else None
        pages = min(1000, max(1, math.ceil(total/page_size))) if total is not None else None
        has_more = page < pages if pages is not None else raw_count >= page_size and page < 1000
        return dict(songs=songs, page=page, page_size=page_size, total=total,
                    total_pages=pages, has_more=has_more)

    def netease(self, query, page, size):
        data = self.get('https://music.163.com/api/search/get/web',
                        {'s':query,'type':1,'offset':(page-1)*size,'limit':size}, 'netease','https://music.163.com/')
        if data.get('code') != 200:
            raise SearchUnavailable('网易云搜索受限，请扫码登录或稍后重试')
        result = data.get('result') or {}; items = result.get('songs') or []
        output = []
        for item in items:
            album = item.get('al') or item.get('album') or {}
            artists = item.get('ar') or item.get('artists') or []
            output.append(song('netease',item.get('id',''),item.get('name'),
                               ' / '.join(a.get('name','') for a in artists),album.get('name'),
                               number(item.get('dt',item.get('duration',0)))//1000,album.get('picUrl'),
                               {'song_id':item.get('id')}))
        return output, result.get('songCount'), len(items)

    def qq(self, query, page, size):
        data = self.get('https://c.y.qq.com/soso/fcgi-bin/search_for_qq_cp',
                        {'w':query,'format':'json','p':page,'n':size},'qq','https://y.qq.com/')
        if data.get('code',0) != 0:
            raise SearchUnavailable('QQ 音乐搜索受限，请检查平台凭据或稍后重试')
        result = (data.get('data') or {}).get('song') or {}; items=result.get('list') or []
        output=[]
        for item in items:
            mid=item.get('songmid',''); album_mid=item.get('albummid','')
            output.append(song('qq',mid,item.get('songname'),
                               ' / '.join(a.get('name','') for a in item.get('singer',[])),
                               item.get('albumname'),item.get('interval'),
                               f'https://y.gtimg.cn/music/photo_new/T002R300x300M000{album_mid}.jpg' if album_mid else '',
                               {'songmid':mid,'song_id':item.get('songid')}))
        return output,result.get('totalnum'),len(items)

    def kuwo(self, query, page, size):
        data=self.get('https://www.kuwo.cn/search/searchMusicBykeyWord',
                      dict(vipver=1,client='kt',ft='music',cluster=0,strategy=2012,encoding='utf8',
                           rformat='json',mobi=1,issubtitle=1,show_copyright_off=1,pn=page-1,rn=size,all=query),
                      'kuwo','https://www.kuwo.cn/')
        if 'abslist' not in data and str(data.get('TOTAL',''))!='0':
            raise SearchUnavailable('酷我音乐搜索暂时不可用，请稍后重试')
        items=data.get('abslist') or [];output=[]
        for item in items:
            identity=str(item.get('MUSICRID','')).removeprefix('MUSIC_')
            output.append(song('kuwo',identity,item.get('SONGNAME'),item.get('ARTIST'),item.get('ALBUM'),
                               item.get('DURATION'),item.get('hts_MVPIC'),{'rid':identity}))
        return output,data.get('TOTAL'),len(items)

    def kugou(self, query, page, size):
        data=self.get('https://songsearch.kugou.com/song_search_v2',
                      dict(keyword=query,platform='WebFilter',format='json',page=page,pagesize=size,userid=-1,
                           clientver='',tag='em',filter=2,iscorrection=1,privilege_filter=0,_=int(time.time()*1000)),
                      'kugou','https://www.kugou.com/')
        if data.get('status',1)!=1 or data.get('error_code',0)!=0:
            raise SearchUnavailable('酷狗音乐搜索暂时不可用，请稍后重试')
        result=data.get('data') or {};items=result.get('lists') or [];output=[]
        for item in items:
            trans=item.get('trans_param') or {};identity=item.get('FileHash') or item.get('SQFileHash') or item.get('HQFileHash') or ''
            extra={'hash':identity,'file_hash':item.get('FileHash'),'sq_hash':item.get('SQFileHash'),
                   'hq_hash':item.get('HQFileHash'),'res_hash':item.get('ResFileHash'),'mv_hash':item.get('MvHash'),
                   'ogg_320_hash':trans.get('ogg_320_hash'),'ogg_128_hash':trans.get('ogg_128_hash'),
                   'audio_id':item.get('Audioid'),'album_audio_id':item.get('MixSongID') or item.get('ID'),
                   'album_id':item.get('AlbumID'),'privilege':item.get('Privilege')}
            output.append(song('kugou',identity,item.get('SongName'),item.get('SingerName'),item.get('AlbumName'),
                               item.get('Duration'),str(item.get('Image') or '').replace('{size}','240'),extra))
        return output,result.get('total'),len(items)

    def migu(self, query, page, size):
        data=self.get('https://pd.musicapp.migu.cn/MIGUM2.0/v1.0/content/search_all.do',
                      dict(ua='Android_migu',version='5.0.1',text=query,pageNo=page,pageSize=size,
                           searchSwitch='{"song":1,"album":0,"singer":0,"tagSong":0,"mvSong":0,"songlist":0,"bestShow":1}'),
                      'migu','https://music.migu.cn/')
        if str(data.get('code','000000')) not in ('000000','200','0'):
            raise SearchUnavailable('咪咕音乐搜索暂时不可用，请稍后重试')
        result=data.get('songResultData') or {};items=result.get('result') or [];output=[]
        for item in items:
            formats=item.get('newRateFormats') or item.get('rateFormats') or item.get('audioFormats') or []
            if not formats:continue
            fmt=max(formats,key=lambda f:{'ZQ24':5,'ZQ':4,'SQ':3,'HQ':2,'PQ':1}.get(f.get('formatType'),0))
            identity=str(item.get('contentId') or '')
            extra={'content_id':identity,'resource_type':fmt.get('resourceType'),'format_type':fmt.get('formatType'),
                   'copyright_id':item.get('copyrightId'),'song_id':item.get('songId'),'album_id':item.get('albumId')}
            artists=item.get('singers') or item.get('artists') or item.get('singerList') or []
            albums=item.get('albums') or [];images=item.get('imgItems') or item.get('albumImgs') or []
            if identity:
                output.append(song('migu',identity+'|'+str(fmt.get('resourceType',''))+'|'+str(fmt.get('formatType','')),
                                   item.get('name') or item.get('songName'),' / '.join(a.get('name','') for a in artists) or item.get('singer'),
                                   albums[0].get('name') if albums else item.get('album'),item.get('duration'),
                                   images[0].get('img') if images else item.get('img1'),extra))
        return output,result.get('totalCount',result.get('total')),len(items)
