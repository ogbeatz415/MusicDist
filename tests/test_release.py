import copy
import json
import subprocess
import zipfile
import pytest
from PIL import Image
from pydantic import ValidationError
from musicdist.models import Release
from musicdist.media import digest, transcode, probe
from musicdist.package import build_package, validate_release

@pytest.fixture
def release_data():
    return {'id':'test-release','artist_id':'test-artist','title':'Test Release','artist':'Test Artist','label':'Test Label',
        'upc':'123456789012','release_date':'2026-12-01','genre':'Instrumental',
        'copyright_line':'2026 Test','phonographic_copyright_line':'2026 Test','rights_confirmed':True,
        'destinations':['spotify','apple_music'],'artwork':'cover.png',
        'tracks':[{'id':'t1','title':'Track One','artist':'Test Artist','isrc':'USABC2600001','explicit':False,
        'instrumental':True,'language':'zxx','credits':[{'name':'Test Composer','role':'composer'}],'master':'master.wav'}]}

@pytest.fixture
def media(tmp_path):
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=440:duration=1',
        '-ar','44100','-ac','2','-c:a','pcm_s16le',str(tmp_path/'master.wav')],check=True)
    Image.new('RGB',(3000,3000),'#335533').save(tmp_path/'cover.png')
    return tmp_path

def test_package_preserves_original_masters(release_data,media):
    release=Release(**release_data)
    dest=media/'handoff.zip'
    result=build_package(release,media,dest)
    assert result['status']=='prepared_not_delivered'
    assert all(d['status']=='blocked' for d in result['deliveries'])
    with zipfile.ZipFile(dest) as z:
        assert z.read('audio/001_USABC2600001.wav')==(media/'master.wav').read_bytes()
        manifest=json.loads(z.read('manifest.json'))
        assert 'master' not in manifest['release']['tracks'][0]
        assert manifest['assets'][1]['sha256']==digest(media/'master.wav')
        assert manifest['assets'][1]['duration_seconds']==pytest.approx(1,abs=.01)
    with pytest.raises(ValueError,match='already exists'):
        build_package(release,media,dest)

@pytest.mark.parametrize('field,value',[('upc','123456789013'),('destinations',['made_up_dsp']),('territories',['ZZ'])])
def test_invalid_release_fields(release_data,field,value):
    release_data[field]=value
    with pytest.raises(ValidationError): Release(**release_data)

def test_duplicate_recordings_blocked(release_data):
    release_data['tracks'].append(copy.deepcopy(release_data['tracks'][0]))
    with pytest.raises(ValidationError): Release(**release_data)

def test_missing_rights_and_lossy_master_blocked(release_data,media):
    transcode(media/'master.wav',media/'preview.mp3')
    release_data['tracks'][0]['master']='preview.mp3'
    release_data['rights_confirmed']=False
    errors,_=validate_release(Release(**release_data),media)
    assert any('rights' in e for e in errors)
    assert any('lossless' in e for e in errors)
    assert probe(media/'preview.mp3')['codec']=='mp3'

def test_artwork_validation(release_data,media):
    Image.new('RGB',(100,100)).save(media/'cover.png')
    errors,_=validate_release(Release(**release_data),media)
    assert any('Artwork' in e for e in errors)

def test_cli_end_to_end(release_data,media):
    (media/'release.json').write_text(json.dumps(release_data))
    result=subprocess.run(['python','-m','musicdist','package',str(media/'release.json'),'--output',str(media/'cli.zip')],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    assert json.loads(result.stdout)['delivery_enabled'] is False
