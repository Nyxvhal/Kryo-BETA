/* Explicit, opt-in TikTok discovery. Never autoplay or present catalogue guesses as fingerprints. */
'use strict';
const TikTokFinder39={
 ready:false,timeoutMs:190000,
 looksLike(value){try{const u=new URL(value);return ['tiktok.com','www.tiktok.com','m.tiktok.com','vm.tiktok.com','vt.tiktok.com'].includes(u.hostname.toLowerCase());}catch{return false;}},
 valid(value){try{const u=new URL(value);return this.looksLike(value)&&u.protocol==='https:'&&!u.username&&!u.password&&(!u.port||u.port==='443')&&( /^\/@[A-Za-z0-9_.-]{1,80}\/video\/\d{10,25}\/?$/.test(u.pathname)||(/^(?:vm|vt)\.tiktok\.com$/.test(u.hostname)&&/^\/[A-Za-z0-9_-]{4,100}\/?$/.test(u.pathname))||/^\/t\/[A-Za-z0-9_-]{4,100}\/?$/.test(u.pathname));}catch{return false;}},
 init(){
  if(this.ready)return;this.ready=true;const form=$('songFinderForm'),tabs=form.querySelector('.finder20-tabs');form.noValidate=true; // Each active mode validates explicitly; hidden inputs must not block another mode.
  const tab=el('button','chip');tab.type='button';tab.dataset.finderMode='tiktok';tab.textContent=t('From TikTok');tab.onclick=()=>SongFinder.setMode('tiktok');tabs.append(tab);
  const panel=el('div','finder20-panel finder39-panel');panel.id='songFinderTikTokPanel';panel.hidden=true;
  panel.innerHTML=`<label for="songFinderTikTokUrl"><span data-tiktok-key="TikTok video link"></span><input id="songFinderTikTokUrl" type="url" maxlength="2048" inputmode="url" autocomplete="off" spellcheck="false" placeholder="https://www.tiktok.com/@creator/video/…"></label><p class="finder-help22" data-tiktok-key="Videos up to 10 minutes and 100 MB."></p><p class="finder-help22" data-tiktok-key="Paste a public video link. Short TikTok links also work. Audio is downloaded temporarily and decoded locally."></p><label class="finder20-offset" for="songFinderTikTokOffset"><span data-tiktok-key="Sample start, seconds"></span><input id="songFinderTikTokOffset" type="number" min="0" max="600" step="1" value="0"></label><label class="finder20-consent"><input id="songFinderTikTokConsent" type="checkbox"><span data-tiktok-key="Allow downloading this TikTok video and sending short acoustic fingerprints to Shazam. The original video is not sent to Shazam. These unofficial services may be unavailable."></span></label><div class="finder20-actions"><button id="songFinderTikTokAnalyze" type="button" class="btn"></button><button id="songFinderTikTokUpload" type="button" class="btn g"></button></div><p class="finder-help22" data-tiktok-key="Private or blocked video? Upload the saved clip using the audio/video tab. Slowed tracks, remixes, speech and noise can prevent recognition."></p>`;
  $('songFinderCancel').before(panel);$('songFinderTikTokAnalyze').onclick=()=>this.search();$('songFinderTikTokUpload').onclick=()=>{SongFinder.setMode('file');$('finderChoose22')?.focus();};
  $('songFinderTikTokUrl').oninput=()=>{if(SongFinder.searching)SongFinder.cancel();};
  const mode=SongFinder.setMode.bind(SongFinder);SongFinder.setMode=m=>{mode(m);panel.hidden=m!=='tiktok';};
  const search=SongFinder.search.bind(SongFinder);SongFinder.search=(...a)=>{if(SongFinder.inputMode==='tiktok')return this.search();const q=$('songFinderQuery').value.trim();if(SongFinder.inputMode==='text'&&this.looksLike(q)){this.open(q);return;}return search(...a);};
  const busy=SongFinder.busy.bind(SongFinder);SongFinder.busy=on=>{busy(on);$('songFinderTikTokAnalyze').disabled=on;};
  const mainSearch=App.search.bind(App);App.search=(q,...a)=>{if(this.looksLike(String(q||'').trim())){App.cancelSearch();this.open(String(q).trim());return Promise.resolve();}return mainSearch(q,...a);};
  // A visible shortcut makes the new entry point discoverable without opening More.
  const entry=el('button','btn g');entry.type='button';entry.id='searchTikTok39';entry.onclick=()=>this.open();$('sTitle').after(entry);
  const lang=App.afterLangChange.bind(App);App.afterLangChange=(...a)=>{const v=lang(...a);this.labels();return v;};this.labels();document.body.classList.add('ui-v39');
 },
 labels(){for(const n of document.querySelectorAll('[data-tiktok-key]'))n.textContent=t(n.dataset.tiktokKey);document.querySelector('[data-finder-mode="tiktok"]').textContent=t('From TikTok');$('songFinderTikTokAnalyze').textContent=t('Find music from TikTok');$('songFinderTikTokUpload').textContent=t('Upload a video instead');$('searchTikTok39').textContent=t('Find music from TikTok');},
 open(url=''){App.go('identify');SongFinder.setMode('tiktok');$('songFinderTikTokUrl').value=url;$('scroll').scrollTop=0;$('songFinderTikTokUrl').focus();},
 note(key){const n=el('p','finder20-result-note');n.textContent=t(key);$('songFinderIdentity').append(n);return n;},
 render(d){
  const identity=$('songFinderIdentity'),results=$('songFinderResults');identity.replaceChildren();results.replaceChildren();
  if(d.recognition){const p=this.note('Recognized from the audio fingerprint');p.append(document.createTextNode(': '+[d.recognition.artist,d.recognition.title].filter(Boolean).join(' — ')));}
  else this.note('No acoustic match. Sound metadata below is only a hint, not a confirmed original.');
  if(d.sound_hint){const p=this.note('TikTok sound credit (unverified)');p.append(document.createTextNode(': '+[d.sound_hint.artist,d.sound_hint.title].filter(Boolean).join(' — ')));}
  if(d.catalogue_error)this.note('Music recognized, but catalogue search is unavailable. Try searching the recognized title later.');
  if(d.warnings?.length)this.note('Some analysis steps were unavailable. Try another excerpt or upload the video.');
  const groups=[['Catalogue versions / possible matches',d.items],['Related tracks — catalogue recommendations, not acoustic matches',d.similar]];
  for(const [key,raw]of groups){const tracks=Array.isArray(raw)?raw.filter(x=>x&&typeof x.id==='string'&&typeof x.title==='string'):[];if(!tracks.length)continue;const section=el('section','finder39-results');const h=el('h2');h.textContent=t(key);section.append(h);tracks.forEach((track,i)=>section.append(Views.trackRow(track,i,tracks)));results.append(section);}
  if(!results.children.length)this.note('No candidates found. Try another description or sample position.');
 },
 async search(){
  if(SongFinder.searching)return;const url=$('songFinderTikTokUrl').value.trim(),status=$('songFinderStatus'),offset=Number($('songFinderTikTokOffset').value);
  status.dataset.error='false';$('songFinderRetry22')?.remove();
  if(!this.valid(url)){status.textContent=t('Use a public HTTPS TikTok video link.');$('songFinderTikTokUrl').focus();return;}
  if(!Number.isFinite(offset)||offset<0||offset>600){status.textContent=t('TikTok sample start must be between 0 and 600 seconds.');$('songFinderTikTokOffset').focus();return;}
  if(!$('songFinderTikTokConsent').checked){status.textContent=t('Allow downloading the video and sending a fingerprint first.');$('songFinderTikTokConsent').focus();return;}
  SongFinder.controller?.abort();const controller=SongFinder.controller=new AbortController(),token=++SongFinder.token;SongFinder.busy(true);$('songFinderIdentity').replaceChildren();$('songFinderResults').replaceChildren();status.textContent=t('Downloading TikTok video → extracting audio → recognizing with Shazam…');let timedOut=false;const timer=setTimeout(()=>{timedOut=true;controller.abort();},this.timeoutMs);
  try{const response=await fetch('/api/song-finder/tiktok',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url,offset,consent:true}),signal:controller.signal});let d;try{d=await response.json();}catch{const failure=Error('Invalid response');failure.detail42='HTTP '+response.status;throw failure;}if(token!==SongFinder.token)return;if(!response.ok||d.error){const failure=Error('TikTok request failed');failure.detail42=typeof d.error==='string'?t(d.error.slice(0,500)):'HTTP '+response.status;throw failure;}this.render(d);status.textContent=d.recognition?t('Audio recognized. Catalogue versions and related tracks are shown separately.'):t('No confirmed original. Check the sound credit or try another excerpt.');}
  catch(e){if(token!==SongFinder.token)return;if(e.name!=='AbortError'||timedOut){status.dataset.error='true';status.textContent=t(timedOut?'TikTok analysis timed out. Try another excerpt or upload the video.':'TikTok analysis failed. Try again or upload the video.');if(!timedOut&&e.detail42)status.textContent+=' '+e.detail42;const retry=el('button','btn g');retry.id='songFinderRetry22';retry.type='button';retry.textContent=t('Try again');retry.onclick=()=>this.search();status.after(retry);}}
  finally{clearTimeout(timer);if(token===SongFinder.token)SongFinder.busy(false);}
 }
};
const bootTikTok39=App.boot.bind(App);App.boot=async function(...a){await bootTikTok39(...a);TikTokFinder39.init();};
