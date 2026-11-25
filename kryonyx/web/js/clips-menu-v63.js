/* Small, isolated video-menu refinement. No changes to general settings. */
'use strict';
const ClipsMenu63={ready:false,
 init(){if(this.ready)return;this.ready=true;const root=$('clips');
 // Keep the original v62 video navigation and watch layout.
 const render=Wave61.render.bind(Wave61);Wave61.render=(...a)=>{const r=render(...a);for(const id of ['pShuffle','pRepeat'])if($(id))$(id).disabled=Wave61.active;return r};
 // Queue edits retain the v62 safety fixes, without its replacement dock.
 for(const key of ['addNext','addLast','removeAt','move','clearQueue']){const old=Player[key].bind(Player);Player[key]=(...a)=>{const before=JSON.stringify([Player.index,...Player.queue.map(t=>t.id)]),removed=key==='removeAt'&&Wave61.active&&a[0]>Player.index?Player.queue[a[0]]:null;if(key==='clearQueue'&&Wave61.active)Wave61.stop(false);const r=old(...a);if(before!==JSON.stringify([Player.index,...Player.queue.map(t=>t.id)])){if(removed){Wave61.history.push(removed.id,Wave61.identity(removed));Wave61.history=Wave61.history.slice(-100)}Player.queueRevision++;Player.order=Player.queue.slice();if(Player.queue[Player.index+1])Player._prefetchKey30='';if(Wave61.active)Wave61.queueEdited62();Player.prefetchNext();Player.saveState()}return r}}

 // Bulk queue actions bypass Player's methods. Invalidate any in-flight
 // recommendations so they cannot overwrite or ignore the user's edits.
 for(const key of ['enqueue','dedupeQueue','undoQueue']){const old=Workspace[key].bind(Workspace);Workspace[key]=(...a)=>{const before=JSON.stringify([Player.index,...Player.queue.map(t=>t.id)]),r=old(...a);if(Wave61.active&&before!==JSON.stringify([Player.index,...Player.queue.map(t=>t.id)])){Player.queueRevision++;Player.order=Player.queue.slice();Player._prefetchKey30='';Wave61.queueEdited62();Player.prefetchNext();Player.saveState()}return r}}
 },

};
const boot63=App.boot.bind(App);App.boot=async function(...a){await boot63(...a);ClipsMenu63.init()};
