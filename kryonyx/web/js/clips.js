/* Clip Studio v4. Native original A/V tracks + independently filled disk cache.
 * Sign-in cookie gate before metadata or media requests. Clip navigation NEVER calls Player.play or changes music history.
 */
'use strict';
const ClipUtils = {
  youtubeId(value) {
    const raw=String(value||'').trim();
    if (/^[A-Za-z0-9_-]{11}$/.test(raw)) return raw;
    try { const u=new URL(raw); if(!['https:','http:'].includes(u.protocol))return null;
      let id='';const host=u.hostname.toLowerCase();
      if(host==='youtu.be')id=u.pathname.split('/')[1];
      else if(['youtube.com','www.youtube.com','m.youtube.com','music.youtube.com','www.youtube-nocookie.com'].includes(host)) id=u.searchParams.get('v')||(/^\/(shorts|embed|live)\//.test(u.pathname)?u.pathname.split('/')[2]:'');
      return /^[A-Za-z0-9_-]{11}$/.test(id||'')?id:null;
    }catch{return null;}
  },
  threshold(job,percent) {const src=Object.values(job.sources||{});return src.length>0&&src.every(s=>s.complete||s.progress==null||s.progress>=percent/100);},
  ahead(media) {if(!media||!media.buffered)return 0; const at=media.currentTime;for(let i=0;i<media.buffered.length;i++)if(media.buffered.start(i)<=at+.1&&media.buffered.end(i)>=at)return Math.max(0,media.buffered.end(i)-at);return 0;},
  ready(media,seconds) {if(!media||media.readyState<3||!Number.isFinite(media.duration))return false;return this.ahead(media)>=Math.min(seconds,Math.max(0,media.duration-media.currentTime-.1));},
  bytes(n){if(n==null)return '—';return n>=1048576?(n/1048576).toFixed(1)+' MiB':Math.round(n/1024)+' KiB';},
  time(n){n=Math.max(0,Math.floor(n||0));return Math.floor(n/60)+':'+String(n%60).padStart(2,'0');},
  captions(text){
    text=String(text).replace(/^\uFEFF/,'').replace(/\r/g,'');
    const stamp=s=>{const p=s.replace(',','.').split(':').map(Number);return p.reduce((a,b)=>a*60+b,0);};
    return text.split(/\n\s*\n/).flatMap(block=>{const ls=block.split('\n'),i=ls.findIndex(s=>s.includes('-->'));if(i<0)return [];const m=ls[i].match(/([\d:. ,]+)\s*-->\s*([\d:.,]+)/);if(!m)return [];const a=stamp(m[1].trim()),b=stamp(m[2].trim());return Number.isFinite(a)&&b>a?[{start:a,end:b,text:ls.slice(i+1).join('\n').replace(/<[^>]*>/g,'')}]:[];});
  }
};
if(typeof module!=='undefined'&&module.exports)module.exports=ClipUtils;
const Clips = {
  video:null,audio:null,track:null,job:null,items:[],token:0,searchToken:0,active:false,muted:false,wantPlay:false,started:false,poll:0,syncTimer:0,original:null,wasPlaying:false,markA:null,markB:null,captionTrack:null,resumes:{},pendingTrack:null,gatedTrack:null,
  init(){
    this.video=$('clipVideo');this.audio=$('clipAudio');if(!this.video)return;
    try{this.resumes=JSON.parse(localStorage.getItem('kryonyx.clip.positions')||'{}');}catch{this.resumes={};}if(!this.resumes||typeof this.resumes!=='object'||Array.isArray(this.resumes))this.resumes={};
    ['navClips','pVideo','nVideo'].forEach(id=>{if($(id))$(id).onclick=()=>this.open(Player.current);});
    const click=(id,fn)=>$(id).onclick=fn;
    click('clipClose',()=>this.close());click('clipCookies',()=>this.setupCookies());
    $('clipSearchForm').onsubmit=e=>{e.preventDefault();this.search($('clipSearch').value);};
    click('clipQueueTab',()=>{this.searchToken++;this.items=[...(Player.queue||[])];this.renderQueue(t("Music queue"));});
    click('clipArtistTab',()=>this.search((this.track?.artist||Player.current?.artist||'')+' official music video'));
    click('clipPlay',()=>this.toggle());click('clipBack',()=>this.seek(this.video.currentTime-10));click('clipFwd',()=>this.seek(this.video.currentTime+10));click('clipNext',()=>this.next());
    click('clipFullPlay',()=>this.toggle());click('clipFullBack',()=>this.seek(this.video.currentTime-10));click('clipFullFwd',()=>this.seek(this.video.currentTime+10));click('clipFullExit',()=>document.exitFullscreen().catch(()=>{}));click('clipFull',()=>this.fullscreen());click('clipPip',async()=>{try{if(!document.pictureInPictureEnabled||!this.video.videoWidth)throw Error(t("Picture-in-picture is unavailable for this browser or video"));if(document.pictureInPictureElement)await document.exitPictureInPicture();else await this.video.requestPictureInPicture();}catch(e){toast(e.message);}});
    click('clipTheater',()=>{$('clips').classList.toggle('theater');$('clipTheater').textContent=$('clips').classList.contains('theater')?t("Normal view"):t("Theatre mode");});
    click('clipSnapshot',()=>this.snapshot());
    $('clipDownload').onclick=e=>{e.preventDefault();this.saveOriginal(this.job);};
    click('clipMarkA',()=>{this.markA=this.video.currentTime;this.markB=null;this.paintAB();});click('clipMarkB',()=>{if(this.markA==null||this.video.currentTime<=this.markA+.2){toast(t("Set point A first, then point B after it"));return;}this.markB=this.video.currentTime;this.paintAB();});click('clipClearAB',()=>{this.markA=this.markB=null;this.paintAB();});
    click('clipErrorRetry',()=>this.track&&this.load(this.track,true));click('clipReload',()=>this.track&&this.load(this.track,true));click('clipCancel',()=>this.control('cancel'));
    click('clipDownloadPause',()=>this.control(this.job?.state==='paused'?'resume':'pause'));
    click('clipJobsRefresh',()=>this.refreshJobs());document.querySelector('.cs-jobs').ontoggle=()=>{if(document.querySelector('.cs-jobs').open)this.refreshJobs();};
    $('clipSeek').oninput=()=>{if(Number.isFinite(this.video.duration))this.seek(this.video.duration*Number($('clipSeek').value)/1000);};
    $('clipVolume').value=String(S.videoVolume??100);$('clipVolume').oninput=()=>{S.videoVolume=Number($('clipVolume').value);this.applyAudio();saveSettings();};
    [['clipQuality','videoQuality',720],['clipStartPercent','clipStartPercent',10],['clipMinBuffer','clipMinBuffer',3],['clipSpeed','clipSpeed',1]].forEach(([id,key,fallback])=>{let val=S[key]??fallback;if(id==='clipQuality'&&![240,360,480,720,1080,1440,2160].includes(+val))val=720;$(id).value=String(val);$(id).onchange=()=>{S[key]=Number($(id).value);saveSettings();if(id==='clipQuality'&&this.track)this.load(this.track);if(id==='clipSpeed')this.applyAudio();this.maybeStart();};});
    [['clipLoop','clipLoop',false],['clipAutoNext','clipAutoNext',true],['clipPrefetch','clipPrefetch',false],['clipKeepDownloading','clipKeepDownloading',false],['clipResume','clipResume',true]].forEach(([id,key,value])=>{$(id).checked=S[key]??value;$(id).onchange=()=>{S[key]=$(id).checked;saveSettings();if(id==='clipPrefetch'&&$(id).checked)this.prefetch();};});
    document.querySelectorAll('[data-clip-tab]').forEach((btn,i,all)=>{btn.onclick=()=>this.tab(btn.dataset.clipTab);btn.onkeydown=e=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;e.preventDefault();const index=e.key==='Home'?0:e.key==='End'?all.length-1:(i+(e.key==='ArrowRight'?1:-1)+all.length)%all.length;all[index].focus();this.tab(all[index].dataset.clipTab);};});
    $('clipCaption').onchange=()=>this.importCaptions();
    this.video.addEventListener('timeupdate',()=>{this.paintTime();if(this.markB!=null&&this.video.currentTime>=this.markB)this.seek(this.markA);if(this.started&&this.active)this.savePosition();});
    this.video.addEventListener('ended',()=>{if($('clipLoop').checked){this.seek(0);this.wantPlay=true;this.maybeStart();}else{this.wantPlay=false;this.stopMedia();if($('clipAutoNext').checked)this.next();}});
    [this.video,this.audio].forEach(media=>{media.addEventListener('canplay',()=>this.maybeStart());media.addEventListener('progress',()=>this.maybeStart());media.addEventListener('waiting',()=>this.stall(media));media.addEventListener('error',()=>{if(!this.active||!media.getAttribute('src'))return;this.wantPlay=false;this.stopMedia();this.showError(t("Decoding or stream error. Retry or choose another quality."));});});
    this.video.addEventListener('seeked',()=>{this.syncAudio(true);this.maybeStart();});
    this.video.addEventListener('playing',()=>{$('clipBusy').hidden=true;this.started=true;this.paintPlay();});
    this.video.addEventListener('pause',()=>this.paintPlay());
    document.addEventListener('keydown',e=>this.onKey(e),true);
    this.applyAudio();
  },
  tab(name){document.querySelectorAll('[data-clip-tab]').forEach(b=>b.setAttribute('aria-selected',String(b.dataset.clipTab===name)));['download','tools','settings'].forEach(n=>$('clipPanel-'+n).hidden=n!==name);},
  status(text){if($('clipStatus').textContent!==text)$('clipStatus').textContent=text;},
  showError(text){this.playError=text;if($('clipErrorText').textContent!==text)$('clipErrorText').textContent=text;$('clipError').hidden=false;$('clipBusy').hidden=true;this.status(text);},
  cookiesReady(){const s=YTCookies.state;return !!s&&(!!s.browser||!!s.present&&!!s.signed_in&&!s.expired);},
  async authorize57(force=false){
    if(!force&&this.cookiesReady()&&Date.now()-(this.cookieAt57||0)<3000)return true;
    if(!this.cookieRequest57)this.cookieRequest57=YTCookies.load(true).finally(()=>{this.cookieAt57=Date.now();this.cookieRequest57=null});
    await this.cookieRequest57;
    if(!this.cookiesReady()){this.lock57();return false}return true;
  },
  lock57(){
    const old=this.job;this.token++;this.searchToken++;this.wantPlay=false;clearTimeout(this.poll);clearInterval(this.syncTimer);this.syncTimer=0;
    if(this.active){this.stopMedia();this.detach();this.job=null;this.started=false;
      if(old&&!['done','error','cancelled'].includes(old.state))api('/api/clips/sessions/'+old.id+'/control',{method:'POST',body:{action:'pause'}}).catch(()=>{});
      if(this.prefetchJob)api('/api/clips/sessions/'+this.prefetchJob+'/control',{method:'POST',body:{action:'pause'}}).catch(()=>{});
      if(typeof Video57!=='undefined')Video57.gate();}
  },
  onCookiesChanged57(){this.paintCookies();if(this.active&&!this.cookiesReady())this.lock57();},
  unlock(){this.paintCookies();},
  paintCookies(){if($('clipCookieState'))$('clipCookieState').textContent=this.cookiesReady()?t('Cookie source configured'):'YouTube cookies required';},
  async setupCookies(){this.returnTrack57=this.gatedTrack||this.track;await this.close();closeModals();Workspace.openSettings();App.openPane('lib');YTCookies.open();if(typeof Video57!=='undefined')Video57.cookieReturn();},
  startSync57(){clearInterval(this.syncTimer);this.syncTimer=setInterval(()=>{if(!this.active||!this.job)return;this.syncAudio();this.maybeStart();this.paintTime();},250);},
  async open(track){
    if(!Video57.ready && App.bootReady){await App.bootReady;return this.open(track);}
    if(!this.active){this.original=Player.current?.id;this.wasPlaying=!!Player.audio&&!Player.audio.paused;this.originalWantPlay=Player.wantPlay;Player.wantPlay=false;Player.xfToken++;Player.xfFrom=null;(Player.deck||[Player.audio]).forEach(a=>a?.pause());if(Player.audio)Player.audio.volume=S.volume/100;this.items=[...(Player.queue||[])];}
    this.active=true;const opening=this.openToken57=(this.openToken57||0)+1;$('clips').classList.add('on');$('clips').setAttribute('aria-hidden','false');this.gatedTrack=track||null;Video57.mode('checking');
    if(!await this.authorize57(true)||!this.active||opening!==this.openToken57)return;this.gatedTrack=null;this.paintCookies();
    if(track?.id)await this.load(track);else{this.token++;clearTimeout(this.poll);this.detach();this.job=null;this.track=null;this.wantPlay=false;this.started=false;this.playError='';$('clipTitle').removeAttribute('data-entity-name');$('clipMeta').removeAttribute('data-entity-name');$('clipError').hidden=true;$('clipEmpty').hidden=false;$('clipBusy').hidden=true;$('clipTitle').textContent=t("Choose a video");$('clipMeta').textContent=t("Current track, queue or original video link");$('clipSource').hidden=true;$('clipDownload').hidden=true;$('clipProgress').value=0;$('clipProgressText').textContent='—';['clipVideoProgress','clipAudioProgress','clipRate','clipBuffer'].forEach(id=>$(id).textContent='—');$('clipDownloadPause').disabled=true;$('clipCancel').disabled=true;$('clipPlay').disabled=true;this.paintTime();this.paintPlay();this.status(t("Choose a video from the queue or paste a YouTube link"));await Video57.catalog();}
  },
  onTrack(){},warm(){},
  savePosition(){if(!$('clipResume').checked||!this.track)return;const now=Date.now();if(now-(this.lastSave||0)<3000)return;this.lastSave=now;this.resumes[this.track.id]={time:this.video.currentTime,updated:now};const entries=Object.entries(this.resumes).sort((a,b)=>b[1].updated-a[1].updated).slice(0,100);this.resumes=Object.fromEntries(entries);try{localStorage.setItem('kryonyx.clip.positions',JSON.stringify(this.resumes));}catch{}},
  stopMedia(){this.video.pause();this.audio.pause();this.paintPlay();},
  detach(){this.stopMedia();[this.video,this.audio].forEach(m=>{m.removeAttribute('src');m.load();});if(this.captionTrack)this.captionTrack.mode='disabled';this.captionTrack=null;$('clipCaption').value='';$('clipBuffer').textContent='—';},
  async close(){
    if(!this.active)return;this.savePosition();this.active=false;this.openToken57=(this.openToken57||0)+1;Video57.abort();this.searchToken++;this.wantPlay=false;this.stopMedia();const closing=++this.token;clearTimeout(this.poll);clearInterval(this.syncTimer);this.syncTimer=0;
    const job=this.job;if(this.prefetchJob&&!$('clipKeepDownloading').checked)api('/api/clips/sessions/'+this.prefetchJob+'/control',{method:'POST',body:{action:'pause'}}).catch(()=>{});if(job&&!$('clipKeepDownloading').checked&&!['done','error','cancelled'].includes(job.state))api('/api/clips/sessions/'+job.id+'/control',{method:'POST',body:{action:'pause'}}).catch(()=>{});
    if(document.pictureInPictureElement)await document.exitPictureInPicture().catch(()=>{});if(document.fullscreenElement)await document.exitFullscreen().catch(()=>{});
    if(closing!==this.token||this.active)return;this.detach();this.job=null;$('clips').classList.remove('on');$('clips').setAttribute('aria-hidden','true');if(Player.current?.id===this.original){Player.wantPlay=!!this.originalWantPlay;if(this.wasPlaying)Player.audio?.play().catch(()=>{});}this.wasPlaying=false;$('navClips')?.focus();
  },
  async load(track,retry=false){
    if(!this.active)return;const request57=this.loadRequest57=(this.loadRequest57||0)+1;if(!await this.authorize57()){this.gatedTrack=track;return}if(!this.active||request57!==this.loadRequest57)return;Video57.abort();Video57.mode('watch');this.startSync57();
    const token=++this.token;clearTimeout(this.poll);this.searchToken++;this.wantPlay=false;this.stopMedia();
    const previous=this.job; if(previous&&!['done','error','cancelled'].includes(previous.state))await api('/api/clips/sessions/'+previous.id+'/control',{method:'POST',body:{action:'pause'}}).catch(()=>{});
    if(token!==this.token||!this.active)return;
    this.detach();this.track={...track};this.job=null;this.playError='';this.started=false;this.markA=this.markB=null;this.paintAB();this.wantPlay=true;this.playPending=false;this.attached=false;this.resumeSet=false;this.paintPlay();
    $('clipTitle').toggleAttribute('data-entity-name',!!track.title);$('clipMeta').toggleAttribute('data-entity-name',!!track.artist);$('clipError').hidden=true;$('clipTitle').textContent=track.title||t("Original music video");$('clipMeta').textContent=track.artist||'YouTube';$('clipSource').hidden=true;$('clipEmpty').hidden=true;$('clipBusy').hidden=false;$('clipBusyText').textContent=t("Finding an available original…");$('clipDownload').hidden=true;this.status(t("Preparing the source"));this.renderQueue();this.paintTime();
    try{const job=await api('/api/clips/sessions',{method:'POST',body:{id:track.id,title:track.title||'',artist:track.artist||'',quality:Number($('clipQuality').value),retry},timeout:15000});if(token!==this.token||!this.active){if(!S.clipKeepDownloading)api('/api/clips/sessions/'+job.id+'/control',{method:'POST',body:{action:'pause'}}).catch(()=>{});return;}this.receive(job);this.watch(token);}
    catch(e){if(token!==this.token)return;if(e.status===403){YTCookies.state=null;this.lock57();return}this.wantPlay=false;$('clipBusy').hidden=true;this.showError(t("Could not open the video: ")+e.message);}
  },
  async watch(token){if(!this.active||token!==this.token||!this.job)return;try{const job=await api('/api/clips/sessions/'+this.job.id,{timeout:10000});if(token!==this.token)return;this.receive(job);}catch(e){if(token===this.token)this.status(t("No server response: ")+e.message);}if(this.active&&token===this.token&&!['done','error','cancelled','paused'].includes(this.job?.state))this.poll=setTimeout(()=>this.watch(token),900);},
  receive(job){
    this.job=job;$('clipPlay').disabled=!job.video_url||['error','cancelled'].includes(job.state);const states={resolving:t("Finding the original"),downloading:t("Downloading in the background"),paused:t("Download paused"),muxing:t("Streams downloaded · merging the file"),done:t("Saved locally · available offline"),error:t("Source error"),cancelled:t("Download cancelled")};
    this.status(this.playError||(job.error?states[job.state]+': '+job.error:states[job.state]||job.state));
    $('clipProgress').value=job.progress??0;$('clipProgressText').textContent=(job.progress==null?(['error','cancelled'].includes(job.state)?'—':t("Determining size")):Math.floor(job.progress*100)+'%')+' · '+ClipUtils.bytes(job.downloaded)+(job.total?' / '+ClipUtils.bytes(job.total):'');
    const sourceText=(s,kind)=>s?(s.progress==null?t("Determining size"):Math.floor(s.progress*100)+'%')+' · '+ClipUtils.bytes(s.downloaded):(kind==='audio'&&job.sources?.video?t("Included in the video stream"):'—');
    $('clipVideoProgress').textContent=sourceText(job.sources?.video,'video');$('clipAudioProgress').textContent=sourceText(job.sources?.audio,'audio');
    $('clipRate').textContent=job.state==='downloading'?ClipUtils.bytes(job.bytes_per_second)+t("/s")+(job.eta_seconds!=null?' · '+ClipUtils.time(job.eta_seconds):''):'—';
    $('clipDownloadPause').textContent=job.state==='paused'?t("Resume download"):t("Pause download");$('clipDownloadPause').disabled=['done','muxing','error','cancelled'].includes(job.state);$('clipCancel').disabled=['done','error','cancelled'].includes(job.state);$('clipDownload').hidden=!job.file_ready;if(job.download_url)$('clipDownload').href=job.download_url;
    $('clipDownloadNote').textContent=job.mux_error?t("Original streams saved and playable. The complete file could not be merged: ")+job.mux_error:t("The complete original will be available after downloading and merging streams without re-encoding. Progress reflects continuously saved data; index reads and distant seeks are counted separately.");
    if(job.video_id){$('clipSource').href='https://www.youtube.com/watch?v='+encodeURIComponent(job.video_id);$('clipSource').hidden=false;}
    $('clipMeta').textContent=(this.track?.artist||'YouTube')+(job.height?' · '+job.height+'p':'')+' · '+(job.audio_url?t("Original video + audio"):job.video_url?t("Combined stream"):t("Source is not ready"));
    if(['error','cancelled'].includes(job.state)){this.wantPlay=false;this.stopMedia();$('clipBusy').hidden=true;if(job.state==='error')this.showError(job.error||t("Source unavailable"));return;}
    if(job.video_url&&!this.attached){this.attached=true;this.video.muted=!!job.audio_url;this.video.src=job.video_url;if(job.audio_url)this.audio.src=job.audio_url;this.applyAudio();}
    this.maybeStart();
    if(job.offline_ready&&$('clipPrefetch').checked)this.prefetch();
  },
  maybeStart(){
    if(!this.active||!this.job||!this.attached)return;
    const v=this.video,a=this.job.audio_url?this.audio:null;
    const bufferText=ClipUtils.ahead(v).toFixed(1)+t(" s")+(a?' / '+ClipUtils.ahead(a).toFixed(1)+t(" s"):'');if($('clipBuffer').textContent!==bufferText)$('clipBuffer').textContent=bufferText;
    if(!this.resumeSet&&v.readyState>=1){this.resumeSet=true;const at=$('clipResume').checked?this.resumes[this.track.id]?.time||0:0;if(at>0&&at<v.duration-2)this.seek(at);}
    if(!this.wantPlay)return;
    const ready=ClipUtils.ready(v,Number($('clipMinBuffer').value))&&(!a||ClipUtils.ready(a,Number($('clipMinBuffer').value)));
    const threshold=this.started||ClipUtils.threshold(this.job,Number($('clipStartPercent').value));
    if(!ready||!threshold){if(v.paused){$('clipBusy').hidden=false;$('clipBusyText').textContent=!threshold?t("Waiting for ")+$('clipStartPercent').value+t("% of each stream…"):t("Buffering video and audio…");}return;}
    if(v.paused&&!this.playPending){this.playPending=true;this.syncAudio(true);const token=this.token;const promises=[v.play()];if(a)promises.push(a.play());Promise.all(promises).then(()=>{if(token===this.token){this.started=true;$('clipBusy').hidden=true;}}).catch(e=>{if(token!==this.token||e.name==='AbortError')return;this.wantPlay=false;this.stopMedia();$('clipBusy').hidden=true;this.playError=e.name==='NotAllowedError'?t("Video ready. Press Play — the browser blocked autoplay."):t("Could not start playback: ")+e.message;this.status(this.playError);}).finally(()=>{if(token===this.token)this.playPending=false;});}
  },
  stall(media){if(!this.active||!this.wantPlay||!this.started||ClipUtils.ahead(media)>.3)return;this.stopMedia();$('clipBusy').hidden=false;$('clipBusyText').textContent=t("Buffering · continuing the download…");},
  syncAudio(force=false){if(!this.job?.audio_url)return;const v=this.video,a=this.audio;if(a.readyState>=1&&(Math.abs(a.currentTime-v.currentTime)>(force?.03:.15)))try{a.currentTime=v.currentTime;}catch{}if(!this.wantPlay||(v.paused&&!this.playPending))a.pause();else if(!v.paused&&a.paused&&!this.audioPending){this.audioPending=true;const token=this.token;a.play().catch(e=>{if(token===this.token&&e.name!=='AbortError'){this.wantPlay=false;this.stopMedia();this.showError(e.message);}}).finally(()=>{this.audioPending=false;});}},
  applyAudio(){if(!this.video)return;const media=this.job?.audio_url?this.audio:this.video;media.volume=Math.max(0,Math.min(1,Number($('clipVolume').value)/100));media.muted=!!this.muted;this.video.muted=!!this.job?.audio_url||!!this.muted;this.video.preservesPitch=this.audio.preservesPitch=true;this.video.playbackRate=this.audio.playbackRate=Number($('clipSpeed').value)||1;},
  toggle(){if(!this.job)return;this.playError='';if(this.wantPlay){this.wantPlay=false;this.stopMedia();$('clipBusy').hidden=true;}else{this.wantPlay=true;this.maybeStart();}this.paintPlay();},
  paintPlay(){['clipPlay','clipFullPlay'].forEach(id=>$(id).textContent=this.wantPlay?t("Pause"):t("Play"));},
  seek(at){if(!Number.isFinite(at)||!Number.isFinite(this.video.duration)||this.video.duration<=0)return;at=Math.max(0,Math.min(Math.max(0,this.video.duration-.05),at));this.video.currentTime=at;if(this.job?.audio_url&&this.audio.readyState>=1&&Number.isFinite(this.audio.duration))this.audio.currentTime=Math.max(0,Math.min(at,this.audio.duration-.05));this.paintTime();},
  paintTime(){const v=this.video,timeText=ClipUtils.time(v.currentTime)+' / '+ClipUtils.time(v.duration);if($('clipTime').textContent!==timeText)$('clipTime').textContent=timeText;const ratio=Number.isFinite(v.duration)&&v.duration>0?v.currentTime/v.duration:0;$('clipSeek').value=String(ratio*1000);$('clipSeek').style.setProperty('--cs-position',(ratio*100)+'%');},
  paintAB(){$('clipAB').textContent=this.markA==null?t("No loop segment selected"):'A '+ClipUtils.time(this.markA)+(this.markB==null?t(" → set point B"):' — B '+ClipUtils.time(this.markB));},
  async fullscreen(){try{if(document.fullscreenElement)await document.exitFullscreen();else await $('clipStage').requestFullscreen();}catch(e){toast(t("Fullscreen unavailable: ")+e.message);}},
  onKey(e){if(this.active&&e.key==='Escape'&&!document.fullscreenElement&&!e.defaultPrevented){e.preventDefault();e.stopImmediatePropagation();this.close();return;}if(!this.active||/INPUT|TEXTAREA|SELECT|BUTTON/.test(e.target.tagName)||e.ctrlKey||e.altKey||e.metaKey)return;const key=e.key.toLowerCase();if(/^[0-9]$/.test(key)){e.preventDefault();e.stopImmediatePropagation();this.seek(this.video.duration*Number(key)/10);return;}const acts={' ':()=>this.toggle(),arrowleft:()=>this.seek(this.video.currentTime-5),arrowright:()=>this.seek(this.video.currentTime+5),j:()=>this.seek(this.video.currentTime-10),l:()=>this.seek(this.video.currentTime+10),f:()=>this.fullscreen(),n:()=>this.next(),m:()=>{this.muted=!this.muted;this.applyAudio();},escape:()=>{if(!document.fullscreenElement)this.close();}};if(acts[key]){e.preventDefault();e.stopImmediatePropagation();acts[key]();}},
  async search(query){
    if(!await this.authorize57()||!this.active)return;
    query=String(query||'').trim();if(!query||!this.active)return;
    const id=ClipUtils.youtubeId(query);if(id){const track={id:'ytvideo:'+id,title:t("Original music video · ")+id,artist:'YouTube'};this.items=[track,...this.items.filter(t=>t.id!==track.id)];await this.load(track);return;}
    if(/^https?:\/\//i.test(query)){toast(t("Enter a youtube.com or youtu.be link to a specific video"));return;}
    await Video57.catalog(query);
  },
  renderQueue(label){if(typeof Video57!=='undefined'&&Video57.ready){Video57.cards(label);return}const list=$('clipList');list.replaceChildren();if(label)$('clipListLabel').textContent=label;if(!this.items.length){const p=document.createElement('p');p.className='cs-note';p.textContent=t("The queue is empty. Paste a video link or search for an artist.");list.append(p);return;}this.items.forEach((track,i)=>{const btn=document.createElement('button');btn.className='cs-item'+(track.id===this.track?.id?' active':'');const img=document.createElement('img');const url=String(track.cover||track.thumbnail||'');img.src=/^https?:\/\//.test(url)||url.startsWith('/img/')?url:'/img/avatars/kryonyx-core.png';img.alt='';img.loading='lazy';img.onerror=()=>{img.onerror=null;img.src='/img/avatars/kryonyx-core.png';};const texts=document.createElement('span'),b=document.createElement('b'),small=document.createElement('small');b.textContent=track.title||t("Video");b.toggleAttribute('data-entity-name',!!track.title);small.textContent=track.artist||'YouTube';small.dataset.entityName='';texts.append(b,small);const n=document.createElement('span');n.textContent=String(i+1).padStart(2,'0');btn.append(img,texts,n);btn.onclick=()=>this.load(track);list.append(btn);});},
  next(){const i=this.items.findIndex(t=>t.id===this.track?.id);const next=this.items[i+1];if(next)this.load(next);else{this.wantPlay=false;this.stopMedia();this.status(t("End of the video queue"));}},
  async prefetch(){if(!this.active||!this.cookiesReady()||!await this.authorize57())return;const i=this.items.findIndex(t=>t.id===this.track?.id),track=this.items[i+1];if(!track)return;const key=track.id+':'+$('clipQuality').value;if(this.prefetched===key)return;this.prefetched=key;try{const job=await api('/api/clips/sessions',{method:'POST',body:{id:track.id,title:track.title||'',artist:track.artist||'',quality:Number($('clipQuality').value)},timeout:10000});this.prefetchJob=job.id;if(!this.active&&!S.clipKeepDownloading)api('/api/clips/sessions/'+job.id+'/control',{method:'POST',body:{action:'pause'}}).catch(()=>{});}catch{this.prefetched=null;}},
  async control(action){if(!this.job)return;if(action==='resume'&&!await this.authorize57())return;const token=this.token;try{const job=await api('/api/clips/sessions/'+this.job.id+'/control',{method:'POST',body:{action},timeout:10000});if(token===this.token){this.receive(job);if(action==='resume'){clearTimeout(this.poll);this.watch(token)}}}catch(e){toast(e.message);}},
  async refreshJobs(){if(!await this.authorize57())return;try{const data=await api('/api/clips/sessions',{timeout:10000});const box=$('clipJobs');box.replaceChildren();if(!data.items.length)box.textContent=t("No downloads");(data.items||[]).forEach(job=>{const row=document.createElement('div');row.className='cs-job';const title=document.createElement('strong');title.textContent=job.title||job.track_id;title.dataset.entityName='';const p=document.createElement('div');p.textContent=({resolving:t("Preparing"),downloading:t("Downloading"),paused:t("Paused"),muxing:t("Merging file"),done:t("Saved"),error:t("Error"),cancelled:t("Cancelled")}[job.state]||job.state)+' · '+(job.progress==null?'—':Math.floor(job.progress*100)+'%')+' · '+(job.height?job.height+'p':t("up to ")+job.quality+'p');const acts=document.createElement('div');acts.className='cs-actions';const watch=document.createElement('button');watch.className='btn g';watch.textContent=t("Watch");watch.onclick=()=>{if(job.quality)$('clipQuality').value=String(job.quality);this.load({id:job.track_id,title:job.title,artist:job.artist},['error','cancelled'].includes(job.state));};acts.append(watch);if(!['done','cancelled','error'].includes(job.state)){const pause=document.createElement('button');pause.className='btn g';pause.textContent=job.state==='paused'?t("Resume"):t("Pause");pause.onclick=async()=>{try{await api('/api/clips/sessions/'+job.id+'/control',{method:'POST',body:{action:job.state==='paused'?'resume':'pause'}});this.refreshJobs();}catch(e){toast(e.message);}};acts.append(pause);}if(job.download_url){const a=document.createElement('a');a.className='btn g';a.textContent=t("Download");a.href=job.download_url;a.download='';a.onclick=e=>{e.preventDefault();this.saveOriginal(job);};acts.append(a);}row.append(title,p,acts);box.append(row);});}catch(e){$('clipJobs').textContent=t("Could not load the list: ")+e.message;}},
  async saveOriginal(job){
    if(!job?.download_url||!job.file_ready){toast(t('The complete clip is not ready yet'));return;}
    if(this.saving||FileSave27.busy){toast(t('Another save dialog is already open'));return;}this.saving=true;FileSave27.busy=true;
    const name='clip-'+(job.video_id||job.id)+'-'+(job.height||job.quality)+'p.'+(job.container||'mp4');
    try{
      if(window.pywebview?.api){
        if(typeof window.pywebview.api.save_clip!=='function')throw Error(t('Restart the updated desktop app to enable Save As'));
        const result=await window.pywebview.api.save_clip(job.id);
        if(result?.error)throw Error(result.error);
        if(result?.saved)toast(t('Clip saved to the selected file'));
        else if(!result?.cancelled)throw Error(t('Could not save the file. Check the source and destination.'));
      }else if(window.showSaveFilePicker){
        // Must be invoked before fetch to retain the browser's user activation.
        const ext=job.container==='webm'?'.webm':'.mp4',mime=job.container==='webm'?'video/webm':'video/mp4';
        const handle=await window.showSaveFilePicker({suggestedName:name,types:[{description:t('Export file'),accept:{[mime]:[ext]}}],excludeAcceptAllOption:true});
        const response=await fetch(job.download_url);if(!response.ok)throw Error('HTTP '+response.status);
        const output=await handle.createWritable();
        try{if(response.body)await response.body.pipeTo(output);else{await output.write(await response.blob());await output.close();}}
        catch(e){await output.abort().catch(()=>{});throw e;}
        toast(t('Clip saved'));
      }else{
        throw Error(t('Save As is unavailable here. Open the desktop app or a browser with a file picker. No file was saved.'));
      }
    }catch(e){if(e.name!=='AbortError')toast(t('Could not save: ')+t(e.message));}
    finally{this.saving=false;FileSave27.busy=false;}
  },
  snapshot(){if(!this.video.videoWidth){toast(t("Wait for a video frame first"));return;}try{const canvas=document.createElement('canvas');canvas.width=this.video.videoWidth;canvas.height=this.video.videoHeight;canvas.getContext('2d').drawImage(this.video,0,0);return FileSave27.save({kind:'frame',name:'clip-frame-'+Math.floor(this.video.currentTime)+'.png',data:canvas.toDataURL('image/png')});}catch(e){toast(t("Frame unavailable: ")+e.message);}},
  async importCaptions(){const f=$('clipCaption').files[0];if(!f)return;if(f.size>1048576){toast(t("Subtitles must be smaller than 1 MiB"));return;}try{const cues=ClipUtils.captions(await f.text());if(!cues.length)throw Error(t("No valid timestamps"));if(this.captionTrack)this.captionTrack.mode='disabled';const track=this.video.addTextTrack('subtitles',f.name,'');cues.slice(0,10000).forEach(c=>track.addCue(new VTTCue(c.start,c.end,c.text)));track.mode='showing';this.captionTrack=track;toast(t("Subtitles added: ")+cues.length);}catch(e){toast(t("Subtitle error: ")+e.message);}}
};
