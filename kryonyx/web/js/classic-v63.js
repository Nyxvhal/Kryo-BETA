/* Classic v63: restore the pre-Lumen shell; retain only reusable video helpers.
   No UI53–56 shell, appearance replacement, rail rewrite or session overlay. */
'use strict';
DEFAULTS.classic63=0;
DEFAULTS.classicBackup63=null;
const UI53={tr(en,ru){return LANG==='ru'?ru:en},n(tag,cls,text){return UI52.node(tag,cls,text)},b(label,ico,fn,cls='btn g'){const b=this.n('button',cls,label);b.type='button';b.dataset.noI18n='';if(ico)b.prepend(UI52.icon(ico));b.onclick=fn;return b}};
const UI56={render(){}}; // Optional artwork hook; no replacement listening panel.
const Classic63={
 ready:false,
 tokens(){const s=getComputedStyle(document.documentElement),get=(name,fallback)=>s.getPropertyValue(name).trim()||fallback;
 const values={bg:get('--bg','#101116'),panel:get('--bg-2','#181a22'),raised:get('--card','#222530'),text:get('--text','#f2f2f7'),muted:get('--muted','#a6a8bb'),line:get('--line','#363944'),accent:get('--accent','#9f80f6'),focus:get('--accent','#9f80f6'),ink: S.light?'#fff':'#111318'};
 for(const [key,value]of Object.entries(values))document.documentElement.style.setProperty('--u52-'+key,value);
 },
 init(){if(this.ready)return;this.ready=true;document.body.classList.add('classic63');
 if(!S.classic63){S.classicBackup63={layout48:S.layout48,workspace:S.workspace,rail:S.rail};S.rail=false;S.workspace={...Workspace.prefs(),sidebarCollapsed:false};S.layout48={...DEFAULTS.layout48};S.classic63=1;Workspace.apply();Design48.apply();saveSettings()}
 this.tokens();UI52.clips();UI52.removeVisualizer();
 const clipNav=$('navClips');if(clipNav){$('sideMore31').before(clipNav);clipNav.onclick=()=>Clips.open(null)}
 $('setFind').placeholder=UI53.tr('Find a setting','Найти настройку');
 const mobile=UI53.b(UI53.tr('Videos','Клипы'),'youtube',()=>Clips.open(null),'');mobile.id='mobClips52';$('mobSettings').before(mobile);
 const lang=App.afterLangChange.bind(App);App.afterLangChange=(...a)=>{const r=lang(...a);UI52.clipLabels();$('setFind').placeholder=UI53.tr('Find a setting','Найти настройку');mobile.lastChild.textContent=UI53.tr('Videos','Клипы');this.tokens();return r};
 const theme=applyTheme;applyTheme=(...a)=>{const r=theme(...a);this.tokens();return r};
 },
};
// Boot52 supplies the compatibility hooks; the visual shell remains classic.
UI52.init=()=>Classic63.init();
UI52.apply=()=>Classic63.tokens();
