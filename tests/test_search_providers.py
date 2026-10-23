import unittest
from unittest.mock import MagicMock,patch
import requests
from search_providers import ProviderSearch,SearchUnavailable


class SearchProvidersTest(unittest.TestCase):
    def setUp(self):self.provider=ProviderSearch(lambda:{'netease':'private-cookie'})

    def test_netease_uses_real_offsets_and_normalizes_metadata(self):
        data={'code':200,'result':{'songCount':53,'songs':[{'id':21,'name':'Song','artists':[{'name':'Singer'}],'album':{'name':'Album'},'duration':180000}]}}
        with patch.object(self.provider,'get',return_value=data) as get:
            page=self.provider.search('query','netease',2,20)
        self.assertEqual(get.call_args.args[1]['offset'],20)
        self.assertEqual(get.call_args.args[1]['limit'],20)
        self.assertEqual((page['page'],page['total_pages'],page['has_more']),(2,3,True))
        self.assertEqual(page['songs'][0]['id'],'21');self.assertEqual(page['songs'][0]['duration'],180)
        self.assertNotIn('private-cookie',str(page))

    def test_all_sources_pass_distinct_page_parameters(self):
        fixtures={
            'qq':({'code':0,'data':{'song':{'totalnum':61,'list':[]}}},'p','n',3),
            'kuwo':({'TOTAL':'61','abslist':[]},'pn','rn',2),
            'kugou':({'status':1,'data':{'total':61,'lists':[]}},'page','pagesize',3),
            'migu':({'songResultData':{'totalCount':61,'result':[]}},'pageNo','pageSize',3),
        }
        for source,(data,page_key,size_key,expected) in fixtures.items():
            with self.subTest(source=source),patch.object(self.provider,'get',return_value=data) as get:
                result=self.provider.search('query',source,3,20)
                params=get.call_args.args[1];self.assertEqual(params[page_key],expected);self.assertEqual(params[size_key],20)
                self.assertEqual(result['total_pages'],4)

    def test_last_empty_and_unknown_total_pages(self):
        for total,count,page,size,more in [(21,1,2,20,False),(0,0,1,20,False),(None,20,1,20,True),(None,3,2,20,False)]:
            response={'code':200,'result':{'songs':[{'id':i+1} for i in range(count)]}}
            if total is not None:response['result']['songCount']=total
            with patch.object(self.provider,'get',return_value=response):
                result=self.provider.search('q','netease',page,size);self.assertEqual(result['has_more'],more)

    def test_platform_restriction_is_not_empty_success(self):
        with patch.object(self.provider,'get',return_value={'code':405}):
            with self.assertRaises(SearchUnavailable):self.provider.search('q','netease',1,20)

    def test_network_errors_are_sanitized(self):
        with patch('search_providers.requests.Session') as session:
            session.return_value.__enter__.return_value.get.side_effect=requests.Timeout('secret url cookie')
            with self.assertRaises(SearchUnavailable) as error:self.provider.search('q','netease',1,20)
        self.assertNotIn('secret',str(error.exception))

    def test_kugou_extra_keeps_download_identifiers(self):
        response={'data':{'total':1,'lists':[{'FileHash':'hash','SongName':'<em>Name</em>','MixSongID':12,'Audioid':13,'AlbumID':'14'}]}}
        with patch.object(self.provider,'get',return_value=response):data=self.provider.search('q','kugou',1,20)
        self.assertEqual(data['songs'][0]['name'],'Name');self.assertIn('album_audio_id',data['songs'][0]['extra'])
