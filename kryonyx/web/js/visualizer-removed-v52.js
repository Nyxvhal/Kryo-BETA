/* v52: no visualizer renderer is loaded. A tiny no-render compatibility facade
   lets older settings/scene plug-ins initialize without creating a canvas,
   media graph, observer, timer, or animation loop. Karaoke owns its own engine. */
'use strict';
const Viz={on:false,root:null,bg:null,ctx:null,spec:null,sctx:null,mood:null,vals:null,peaks:null,w:0,h:0,sw:0,sh:0,dt:0,k:0,last:0,
 build(){},apply(){},center(){return null;},drawBg(){},drawSpectrum(){},frame(){},mountColors(){},onTime(){},paint(){},paintButtons(){},recolor(){},repaintColors(){},reset(){this.on=false;},resize(){},sense(){return null;},setVars(){},setMode(){this.on=false;},setPlaying(){},size(){return false;}
};
