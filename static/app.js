'use strict';
const $ = id => document.getElementById(id);
let release = null, artwork = null, trackAssets = {};
const template = {id:'release-001',artist_id:'bay-beatz',title:'Your Release',artist:'Bay Beatz',label:'Your Label',upc:'REPLACE_WITH_ASSIGNED_UPC',release_date:'2026-12-01',genre:'Hip-Hop',copyright_line:'2026 Your Rights Holder',phonographic_copyright_line:'2026 Your Rights Holder',rights_confirmed:false,territories:['Worldwide'],destinations:['spotify','apple_music','amazon_music','youtube_music','tidal','deezer'],tracks:[{id:'track-001',title:'Your Track',artist:'Bay Beatz',isrc:'REPLACE_WITH_ASSIGNED_ISRC',explicit:false,instrumental:true,language:'zxx',credits:[{name:'Your Composer Name',role:'composer'}]}]};
$('metadata').value = JSON.stringify(template,null,2);
async function api(path, options={}) {
  const response = await fetch(path,{...options,headers:{'Authorization':'Bearer '+$('token').value,'Content-Type':'application/json',...(options.headers||{})}});
  if(!response.ok){ const result=await response.json(); throw new Error(typeof result.detail==='string'?result.detail:JSON.stringify(result.detail)); }
  return response;
}
async function run(button, output, task){
  button.disabled=true; $(output).textContent='Working…';
  try { await task(); } catch(error){$(output).textContent=error.message;} finally{button.disabled=false;}
}
$('connect').onclick = e => run(e.target,'connection',async()=>{const destinations=await(await api('/destinations')).json();$('connection').textContent='Connected. '+destinations.length+' destinations available for planning; delivery connections pending.';});
$('import').onchange = async e => {const file=e.target.files[0];if(file){try{$('metadata').value=JSON.stringify(JSON.parse(await file.text()),null,2);}catch{$('saved').textContent='This file is not valid JSON.';}}};
$('save').onclick = e => run(e.target,'saved',async()=>{
  const data=JSON.parse($('metadata').value);
  await api('/releases',{method:'POST',body:JSON.stringify(data)});
  release=data;artwork=null;trackAssets={};$('assets').replaceChildren();
  addAsset('Cover artwork','artwork',null,'.jpg,.jpeg,.png');
  data.tracks.forEach(t=>addAsset(t.title,'master',t.id,'.wav,.flac,.m4a'));
  $('saved').textContent='Draft saved. Upload each asset below. To revise metadata, create a new draft ID.';
});
function addAsset(title,kind,trackId,accept){
  const row=document.createElement('div');row.className='asset';
  const label=document.createElement('label');label.textContent=title;
  const file=document.createElement('input');file.type='file';file.accept=accept;label.append(file);row.append(label);
  const button=document.createElement('button');button.textContent='Upload';
  const status=document.createElement('p');status.className='hint';row.append(button,status);$('assets').append(row);
  button.onclick=async()=>{
    if(!file.files[0]){status.textContent='Choose a file first.';return;}
    button.disabled=true;file.disabled=true;
    try{
      const blob=file.files[0];const max=kind==='artwork'?30*1024*1024:1024**3;
      if(blob.size>max)throw new Error('File exceeds the upload size limit.');
      const extension='.'+blob.name.split('.').pop().toLowerCase();
      const grant=await(await api('/uploads',{method:'POST',body:JSON.stringify({artist_id:release.artist_id,release_id:release.id,kind,track_id:trackId,extension})})).json();
      status.textContent='Uploading '+blob.name+'…';
      const result=await fetch(grant.upload_url,{method:'PUT',headers:grant.headers,body:blob});
      if(!result.ok)throw new Error('Upload failed ('+result.status+'). Check storage CORS and your connection.');
      if(kind==='artwork')artwork=grant.asset_id;else trackAssets[trackId]=grant.asset_id;
      status.textContent='Uploaded. '+(kind==='master'?'Processing will appear below.':'Artwork is validated during packaging.');
    }catch(err){status.textContent=err.message;}finally{button.disabled=false;file.disabled=false;}
  };
}
$('refresh').onclick=e=>run(e.target,'status',async()=>{
  if(!release)throw new Error('Create a draft first.');
  const item=await(await api('/artists/'+encodeURIComponent(release.artist_id)+'/releases/'+encodeURIComponent(release.id))).json();
  $('status').textContent=item.assets.map(a=>`${a.track_id||'Artwork'} · ${a.asset_id.slice(0,8)} · ${a.state}${a.error?' ('+a.error+')':''}`).join('\n')||'No uploads yet.';
});
$('package').onclick=e=>run(e.target,'result',async()=>{
  if(!release||!artwork)throw new Error('Create a draft and upload artwork and all masters first.');
  const response=await api('/packages',{method:'POST',body:JSON.stringify({artist_id:release.artist_id,release_id:release.id,artwork_asset_id:artwork,track_assets:trackAssets})});
  const url=URL.createObjectURL(await response.blob());const a=document.createElement('a');a.href=url;a.download=release.upc+'-prepared.zip';a.click();setTimeout(()=>URL.revokeObjectURL(url),30000);
  $('result').textContent='Package prepared and downloaded. No release has been sent to a DSP.';
});
