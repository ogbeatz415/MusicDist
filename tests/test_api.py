import pytest
from fastapi.testclient import TestClient
from musicdist.api import app
from musicdist.store import LocalStore
from musicdist import storage

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('MUSICDIST_ADMIN_TOKEN','a'*48)
    store=LocalStore(str(tmp_path/'catalog.sqlite'))
    monkeypatch.setattr('musicdist.api.get_store',lambda:store)
    with TestClient(app) as c:
        yield c,store

def draft():
    return {'id':'r1','artist_id':'a1','title':'Release','artist':'Artist','label':'Label',
        'upc':'123456789012','release_date':'2026-12-01','genre':'Jazz','copyright_line':'2026 Owner',
        'phonographic_copyright_line':'2026 Owner','rights_confirmed':True,'destinations':['spotify'],
        'tracks':[{'id':'t1','title':'Song','artist':'Artist','isrc':'USABC2600001','explicit':False,'instrumental':True,
                   'credits':[{'name':'Owner','role':'composer'}]}]}
AUTH={'Authorization':'Bearer '+'a'*48}

def test_auth_and_fail_closed(client,monkeypatch):
    c,_=client
    assert c.get('/destinations').status_code==401
    assert c.get('/health/live').json()['delivery_enabled'] is False
    assert c.get('/destinations',headers=AUTH).status_code==200
    monkeypatch.delenv('MUSICDIST_ADMIN_TOKEN')
    assert c.get('/destinations',headers=AUTH).status_code==503

def test_create_no_overwrite_and_isolation(client):
    c,_=client
    assert c.post('/releases',json=draft(),headers=AUTH).status_code==201
    assert c.post('/releases',json=draft(),headers=AUTH).status_code==409
    assert c.get('/artists/other/releases/r1',headers=AUTH).status_code==404
    data=draft();data['artwork']='/etc/passwd'
    assert c.post('/releases',json=data,headers=AUTH).status_code==422
    assert c.post('/deliveries',headers=AUTH).status_code==409

def test_upload_reservation_restricted_to_track(client,monkeypatch):
    c,store=client
    c.post('/releases',json=draft(),headers=AUTH)
    calls=[]
    def grant(container,blob):
        calls.append((container,blob));return {'upload_url':'https://example.invalid','method':'PUT'}
    monkeypatch.setattr(storage,'upload_url',grant)
    body={'artist_id':'a1','release_id':'r1','kind':'master','track_id':'t1','extension':'.wav'}
    response=c.post('/uploads',json=body,headers=AUTH)
    assert response.status_code==200
    asset=response.json()['asset_id']
    assert calls==[('incoming-tracks',f'a1/r1/{asset}.wav')]
    assert store.get('a1','asset_'+asset)['state']=='awaiting_upload'
    body['track_id']='unrelated'
    assert c.post('/uploads',json=body,headers=AUTH).status_code==422

def test_package_requires_all_tracks(client):
    c,store=client;c.post('/releases',json=draft(),headers=AUTH)
    assert c.post('/packages',json={'artist_id':'a1','release_id':'r1','artwork_asset_id':'x','track_assets':{}},headers=AUTH).status_code==422

def test_sas_is_create_only_https(monkeypatch):
    from types import SimpleNamespace
    class Service:
        account_name='account'
        def get_user_delegation_key(self,start,end): return 'key'
        def get_blob_client(self,container,name): return SimpleNamespace(url='https://account.blob.core.windows.net/'+container+'/'+name)
    captured={}
    monkeypatch.setattr(storage,'service',lambda:Service())
    def sas(**kw):captured.update(kw);return 'signed'
    monkeypatch.setattr(storage,'generate_blob_sas',sas)
    result=storage.upload_url('incoming-tracks','a/r/id.wav')
    assert str(captured['permission'])=='c'
    assert captured['protocol']=='https'
    assert captured['blob_name']=='a/r/id.wav'
    assert result['upload_url'].endswith('/a/r/id.wav?signed')

def test_worker_reraises_and_records_failure(monkeypatch,tmp_path):
    import function_app
    store=LocalStore(str(tmp_path/'catalog.sqlite'))
    asset={'id':'asset_id','asset_id':'id','partitionKey':'a','type':'asset','release_id':'r',
        'track_id':'t','kind':'master','blob':'a/r/id.wav','state':'awaiting_upload'}
    store.put(asset)
    monkeypatch.setenv('CATALOG_BACKEND','cosmos')
    monkeypatch.setattr(function_app,'get_store',lambda:store)
    class BadBlob:
        name='incoming-tracks/a/r/id.wav'
        def read(self,size):raise OSError('simulated interrupted read')
    fn=function_app.audio_transcoder_trigger.build().get_user_function()
    with pytest.raises(OSError):fn(BadBlob())
    assert store.get('a','asset_id')['state']=='failed'

def test_complete_api_package_flow(client,monkeypatch,tmp_path):
    import subprocess,shutil,zipfile,io,json
    from types import SimpleNamespace
    from PIL import Image
    c,store=client
    c.post('/releases',json=draft(),headers=AUTH)
    master=tmp_path/'source.wav';cover=tmp_path/'source.png'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=duration=1','-ac','2','-ar','44100','-c:a','pcm_s16le',str(master)],check=True)
    Image.new('RGB',(3000,3000)).save(cover)
    for id,kind,track,ext in [('audio','master','t1','.wav'),('cover','artwork',None,'.png')]:
        store.put({'id':'asset_'+id,'asset_id':id,'partitionKey':'a1','type':'asset','release_id':'r1',
            'kind':kind,'track_id':track,'state':'processed' if kind=='master' else 'awaiting_upload',
            'container':'incoming-tracks' if kind=='master' else 'release-artwork','blob':f'a1/r1/{id}{ext}'})
    def download(container,name,path): shutil.copyfile(master if name.endswith('.wav') else cover,path)
    monkeypatch.setattr(storage,'download',download)
    monkeypatch.setattr(storage,'service',lambda:SimpleNamespace(get_blob_client=lambda *a:SimpleNamespace(get_blob_properties=lambda:SimpleNamespace(size=1024))))
    response=c.post('/packages',headers=AUTH,json={'artist_id':'a1','release_id':'r1','artwork_asset_id':'cover','track_assets':{'t1':'audio'}})
    assert response.status_code==200,response.text
    with zipfile.ZipFile(io.BytesIO(response.content)) as z:
        m=json.loads(z.read('manifest.json'))
        assert m['release']['tracks'][0]['asset_id']=='audio'
        assert z.read('audio/001_USABC2600001.wav')==master.read_bytes()
    assert store.list('a1','package')[0]['state']=='prepared_not_delivered'
    monkeypatch.setenv('MAX_PACKAGE_BYTES','100')
    assert c.post('/packages',headers=AUTH,json={'artist_id':'a1','release_id':'r1','artwork_asset_id':'cover','track_assets':{'t1':'audio'}}).status_code==413
