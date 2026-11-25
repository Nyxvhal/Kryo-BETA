/* Pure timing helpers shared by the existing karaoke renderers. No clock/loop. */
'use strict';
const KaraokeTiming = {
  progress(time, unit) {
    const a=Number(unit.start ?? unit.time), b=Number(unit.end);
    if (!Number.isFinite(a) || !Number.isFinite(b)) return 0;
    if (b<=a) return time>=a?1:0;
    return Math.max(0,Math.min(1,(time-a)/(b-a)));
  },
  wordProgress(time,word,mode='word') {
    if(mode!=='syllable'||!word.syllables?.length)return this.progress(time,word);
    const units=word.syllables;
    const total=units.reduce((s,u)=>s+Array.from(String(u.text||'')).length,0);
    if(!total)return this.progress(time,word);
    return units.reduce((s,u)=>s+Array.from(String(u.text||'')).length*this.progress(time,u),0)/total;
  },
  index(units,time) {
    let lo=0,hi=units.length-1,found=-1;
    while(lo<=hi){const mid=(lo+hi)>>1;if(Number(units[mid].start??units[mid].time)<=time){found=mid;lo=mid+1;}else hi=mid-1;}
    return found;
  },
  units(line, mode='word') {
    const words=line.words||[];
    if(mode==='line'||!words.length)return [];
    const out=[];
    let cursor=0, text=String(line.text||'');
    for(const word of words){
      // Preserve punctuation/spacing from the source, not a space between every
      // CJK token. Explicit whitespace supplied by ASR is also preserved.
      const token=String(word.text||'').trim();
      if(!token)return [];
      const at=text.indexOf(token,cursor);
      // Inconsistent words must never duplicate or replace the visible source.
      if(at<cursor)return [];
      const before=at>=cursor?text.slice(cursor,at):String(word.text||'').match(/^\s*/)[0];
      const syllables=mode==='syllable'&&Array.isArray(word.syllables)&&word.syllables.length&&
        word.syllables.map(s=>String(s.text)).join('')===token?word.syllables:null;
      (syllables||[word]).forEach((unit,i)=>out.push({unit,text:syllables?unit.text:token,before:i===0?before:''}));
      if(at>=cursor)cursor=at+token.length;
    }
    if(out.length)out[out.length-1].after=text.slice(cursor);
    return out;
  },
  paint(node,progress) {
    const p=Math.round(progress*1000)/10;
    if(node.__karaokeProgress===p)return;
    node.__karaokeProgress=p;node.style.setProperty('--wp',p+'%');node.classList.toggle('lit',p>=100);
  }
};
if(typeof module!=='undefined')module.exports=KaraokeTiming;
