'use strict';
const assert=require('assert/strict'),fs=require('fs'),vm=require('vm');
const a={id:'a',title:'A'},b={id:'b',title:'B'},c={id:'c',title:'C'};
const sandbox={S:{shuffle:false},Workspace:{listVisible:[a,b],listState:{type:'playlist',id:7}},Views:{markPlaying(){},renderQueue(){}},toast(){},t:x=>x,Date,api:async()=>({value:sandbox.saved})};vm.createContext(sandbox);vm.runInContext(fs.readFileSync(__dirname+'/../kryonyx/web/js/player.js','utf8')+'\nglobalThis.subject=Player;',sandbox);const p=sandbox.subject;
p.load=function(){this.current=this.queue[this.index]};p.audio={currentTime:4};p.paintTrack=p.paintTime=p.paintState=()=>{};
let count=0;function check(name,value){assert(value,name);count++}
p.playList([a,b],false,{id:7});check('explicit playlist context normalized',p.playlistContext.id==='7');
check('queue revision increments on playlist start',p.queueRevision===1);
p.index=1;p.load();check('moving to next track keeps source',p.playlistContext.trackIds.includes(p.current.id));
const snapshot=p.snapshot();check('snapshot keeps context',snapshot.playlistContext.id==='7'&&snapshot.index===1&&snapshot.position===4);
p.play(a,[a,b],0);check('unrelated list clears source even for same tracks',p.playlistContext===null);
p.play(a,sandbox.Workspace.listVisible,0);check('playlist row derives context only from visible source list',p.playlistContext.id==='7');
p.play(c);check('single unrelated track invalidates source',p.playlistContext===null);
sandbox.Workspace.listState={type:'liked'};p.playList(sandbox.Workspace.listVisible,false);check('liked tracks have distinct source',p.playlistContext.id==='liked');
(async()=>{sandbox.saved=snapshot;p.current=null;await p.restoreState();check('restore keeps playlist source and does not autoplay',p.playlistContext.id==='7'&&p.current.id==='b'&&p.staged===true);
sandbox.saved={...snapshot,playlistContext:{id:'7',trackIds:['not-in-queue']}};p.current=null;await p.restoreState();check('invalid persisted source discarded',p.playlistContext===null);
sandbox.saved={...snapshot,playlistContext:{id:7,trackIds:['a','b']}};p.current=null;await p.restoreState();check('malformed persisted source rejected',p.playlistContext===null);
console.log('PLAYLIST_STATE_V18_PASS',count);})().catch(e=>{console.error(e);process.exit(1)});
