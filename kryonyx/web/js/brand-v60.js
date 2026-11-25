/* Shared original identity. Explicit custom avatars and real track artwork remain user-owned. */
'use strict';
const Brand60={ready:false,
 init(){if(this.ready)return;this.ready=true;document.body.classList.add('brand60');
 const brand=$('clips').querySelector('.video-brand57');brand.querySelector(':scope>svg')?.remove();const logo=document.createElement('img');logo.id='videoBrand60';logo.alt='Kryo';logo.width=32;logo.height=32;brand.prepend(logo);
 const old=Avatars.paint.bind(Avatars);Avatars.paint=(...a)=>{const result=old(...a);this.paint();return result};this.paint();
 const render=UI56.render.bind(UI56);UI56.render=(...a)=>{const result=render(...a);this.paintPanel();return result};this.paintPanel();
 const empty=$('clipEmpty');empty.querySelector(':scope>svg')?.remove();if(!empty.querySelector('img')){const img=document.createElement('img');img.src='/img/avatars/kryonyx-core.png';img.alt='Kryo';empty.prepend(img)}
 },
 paintPanel(){const img=$('sessionArt56'),cover=$('sessionCover56');if(!img||!cover)return;const track=Player.current;if(!track?.thumbnail){const url=Avatars.src(Avatars.id||S.avatar||'kryonyx-core');if(img.getAttribute('src')!==url)img.src=url;img.hidden=false;cover.classList.add('has-art56');cover.classList.add('brand-empty60')}else cover.classList.remove('brand-empty60')},
 paint(){const chosen=Avatars.id||S.avatar||'kryonyx-core',url=Avatars.src(chosen);if($('videoBrand60'))$('videoBrand60').src=url;if(!Player.current?.thumbnail){for(const id of ['pArt','nArt'])if($(id)){$(id).src=url;$(id).classList.remove('ph');$(id).alt='Kryo'}}}
};
const boot60=App.boot.bind(App);App.boot=async function(...a){await boot60(...a);Brand60.init()};
