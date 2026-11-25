'use strict';
const {chromium}=require('playwright'),assert=require('node:assert/strict');
(async()=>{
  const b=await chromium.launch({executablePath:process.env.CHROMIUM||'/usr/local/bin/chromium',args:['--no-sandbox']});
  const c=await b.newContext();
  const track={id:'test:queue-state',title:'Queue state',artist:'Test',duration:60};
  let settings={settingsRev:8,upgrade30:true,repair33:true},state={player:{queue:[track],index:0,position:12}},writes=[],errors=[];
  await c.route('**/api/**',async r=>{
    const u=new URL(r.request().url()),method=r.request().method();
    if(u.pathname==='/api/settings') { if(method==='PUT')settings={...settings,...r.request().postDataJSON()};return r.fulfill({json:method==='GET'?settings:{ok:true}}); }
    if(u.pathname==='/api/state'||u.pathname==='/api/state/beacon') {
      if(method!=='GET'){const data=r.request().postDataJSON();state[data.key]=data.value;writes.push(data);return r.fulfill({json:{ok:true}});}
      return r.fulfill({json:{value:state[u.searchParams.get('key')]??null}});
    }
    return r.fulfill({json:{ok:true,items:[],sources:[],stats:{}}});
  });
  const p=await c.newPage();p.on('pageerror',e=>errors.push(e.message));
  try {
    await p.goto('http://127.0.0.1:8766');
    await p.waitForFunction(()=>typeof Player!=='undefined'&&Player.current?.id==='test:queue-state');
    assert.equal(await p.evaluate(()=>Player.staged),true,'restored state must not autoplay');
    assert.equal(await p.evaluate(()=>Player.snapshot().position),12,'restored position must survive saving before playback');
    await p.evaluate(()=>Player.saveState(true));await p.waitForTimeout(150);
    assert.equal(state.player.position,12,'saving a staged track must keep its position');
    await p.reload();await p.waitForFunction(()=>Player.current?.id==='test:queue-state');
    assert.equal(await p.evaluate(()=>Player.resumeAt),12,'position survives another restart without playback');
    await p.evaluate(()=>Player.removeAt(0));
    await p.waitForTimeout(1500);
    assert.deepEqual(state.player.queue,[],'removing the last track must persist the empty queue');
    await p.reload();await p.waitForFunction(()=>typeof Player!=='undefined'&&Player.audio);
    await p.waitForTimeout(700);
    assert.equal(await p.evaluate(()=>Player.current),null,'removed track must not return after restart');
    assert.equal(await p.evaluate(()=>Player.queue.length),0);
    await p.evaluate(()=>{setLang('ru');Workspace.openQueue()});
    assert(await p.locator('#queue').isVisible(),'empty queue drawer opens');
    if(process.env.KRYO_QUEUE_SHOT){await p.waitForTimeout(700);await p.screenshot({path:process.env.KRYO_QUEUE_SHOT})}
    const result=await p.evaluate(()=>{const q=Array.from({length:700},(_,i)=>({id:'test:'+i}));Player.queue=q;Player.index=550;Player.current=q[550];return Player.snapshot()});
    assert.equal(result.queue.length,500);assert.equal(result.queue[result.index].id,'test:550','snapshot must contain current track even beyond first 500');
    await p.evaluate(()=>{navigator.sendBeacon=()=>false;Player.saveState(true,true)});
    await p.waitForTimeout(250);
    assert.equal(state.player.queue[state.player.index].id,'test:550','failed beacon falls back to normal save');
    await p.reload();
    await p.waitForFunction(()=>Player.current?.id==='test:550');
    assert.equal(await p.evaluate(()=>Player.staged&&Player.queue[Player.index].id==='test:550'),true,'long queue restores the correct track without autoplay');
    assert.deepEqual(errors,[],'no page errors');
    console.log('QUEUE_STATE_V73_PASS restored, empty queue, reload, long queue, failed beacon, no page errors');
  }finally{await b.close()}
})().catch(e=>{console.error(e);process.exit(1)});
