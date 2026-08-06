export type MusicPhase = "idle" | "investigating" | "caution" | "complete";
export type MusicalAccent = "badge" | "dossier";
type Role = "pad" | "bass" | "lead" | "counter" | "pulse" | "air";
type Instrument =
  | "strings" | "cello" | "piano" | "french-horn" | "low-brass"
  | "solo-violin" | "bassoon" | "clarinet" | "choir" | "glass-harmonica"
  | "harp" | "electric-cello" | "timpani" | "taiko" | "frame-drum"
  | "woodblock" | "bowed-cymbal" | "air" | "baritone-guitar"
  | "pizzicato-strings" | "analog-strings" | "synth-bass" | "gated-snare"
  | "string-ostinato";
type Voice = {
  instrument: Instrument; wave: OscillatorType; attack: number; release: number;
  decay: number; sustain: number; filter: number; gain: number; pan: number;
  vibrato: number;
};
export type MusicEvent = { at: number; duration: number; midi: number; gain: number; role: Role; noise?: boolean };
type ThemeScore = {
  identity: string; root: number; bpm: number; meter: number; phraseBars: number;
  scale: readonly number[]; motif: readonly number[]; answer: readonly number[];
  cadence: readonly number[]; rhythm: readonly number[]; chords: readonly (readonly number[])[];
  progression: readonly number[]; pulse: readonly number[]; form: readonly number[];
  strategy: "measured" | "stop-time" | "crooked" | "orbital" | "chamber" | "signals" | "pursuit";
  voices: Readonly<Record<Role, Voice>>;
};

const instrumentWave = (instrument: Instrument): OscillatorType =>
  ["piano", "harp", "timpani", "taiko", "frame-drum", "woodblock", "baritone-guitar", "pizzicato-strings", "gated-snare", "string-ostinato"].includes(instrument) ? "triangle" : "sine";
const voice = (
  lead: Instrument, bass: Instrument, pad: Instrument, pulse: Instrument,
  color = 1, overrides:Partial<Record<Role,Partial<Voice>>> = {},
): Record<Role, Voice> => {
  const base:Record<Role,Voice>=({
  pad:{instrument:pad,wave:instrumentWave(pad),attack:.42,release:1.5,decay:1.2,sustain:.82,filter:2200*color,gain:.052,pan:-.18,vibrato:.0018},
  bass:{instrument:bass,wave:instrumentWave(bass),attack:.055,release:.5,decay:.55,sustain:.72,filter:1200*color,gain:.12,pan:0,vibrato:.001},
  lead:{instrument:lead,wave:instrumentWave(lead),attack:.07,release:.65,decay:.8,sustain:.7,filter:4200*color,gain:.07,pan:.16,vibrato:.003},
  counter:{instrument:lead,wave:instrumentWave(lead),attack:.12,release:.8,decay:.75,sustain:.65,filter:3000*color,gain:.028,pan:-.34,vibrato:.0025},
  pulse:{instrument:pulse,wave:instrumentWave(pulse),attack:.004,release:.3,decay:.12,sustain:.08,filter:1700*color,gain:.04,pan:.1,vibrato:0},
  air:{instrument:"air",wave:"sine",attack:.8,release:2.2,decay:1.8,sustain:.75,filter:1200*color,gain:.012,pan:.38,vibrato:.0008},
  });
  for(const role of Object.keys(overrides) as Role[])base[role]={...base[role],...overrides[role]};
  return base;
};

// Paired identity fields are parity-tested against core/music.py. Musical
// material is original; no melody or cue is transcribed from another score.
export const SCORE_BIBLES: Record<string, ThemeScore> = {
  default:{identity:"Default (Analyst)",root:45,bpm:108,meter:4,phraseBars:4,scale:[0,2,4,5,7,9,10],motif:[0,1,3,2,4],answer:[4,2,3,1,0],cadence:[4,2,0],rhythm:[1,1,.5,.5,2],chords:[[0,2,4],[3,5,0],[4,6,1],[0,2,4]],progression:[0,1,2,0],pulse:[1,0,0,0,1,0,0,0],form:[.5,.7,1,.62],strategy:"measured",voices:voice("piano","cello","strings","timpani",1,{counter:{instrument:"clarinet",pan:-.2},lead:{decay:.7,sustain:.42}})},
  chuck_norris:{identity:"Chuck Norris",root:38,bpm:132,meter:4,phraseBars:4,scale:[0,2,4,5,7,9,10],motif:[0,4,3,5,2],answer:[5,2,4,1,0],cadence:[5,2,0],rhythm:[.5,.5,1,.5,1.5],chords:[[0,2,4],[3,5,1],[4,6,2],[0,2,4]],progression:[0,2,1,0],pulse:[1,0,0,1,1,0,1,0],form:[.58,.78,1,.52],strategy:"stop-time",voices:voice("french-horn","baritone-guitar","strings","timpani",.9,{lead:{attack:.035,release:.36,pan:.25,gain:.082},bass:{attack:.004,decay:.16,sustain:.18,release:.28,filter:1800,gain:.13},counter:{instrument:"low-brass",attack:.08,release:.55,pan:-.42,gain:.035},pulse:{gain:.058,pan:-.25},pad:{gain:.04}})},
  full_troll:{identity:"Troll",root:43,bpm:118,meter:7,phraseBars:2,scale:[0,2,4,6,7,9,10],motif:[0,3,1,4,2,1],answer:[5,2,4,1,0],cadence:[6,1,0],rhythm:[.5,.5,1,.5,.5,1],chords:[[0,2,4],[3,5,1],[1,4,0],[0,2,4]],progression:[0,2,1,0],pulse:[1,0,1,0,1,0,0],form:[.52,.84,.66,.56],strategy:"crooked",voices:voice("bassoon","pizzicato-strings","strings","woodblock",1.05,{bass:{attack:.004,decay:.12,sustain:.12,release:.22,pan:-.12},counter:{instrument:"clarinet",attack:.025,release:.28,pan:.5},pulse:{pan:-.5},air:{instrument:"bowed-cymbal",gain:.009}})},
  hal9000:{identity:"HAL9000",root:36,bpm:76,meter:5,phraseBars:2,scale:[0,2,4,6,8,10],motif:[0,3,2,4,1],answer:[1,4,2,3,0],cadence:[3,1,0],rhythm:[1.5,.5,.5,1,1.5],chords:[[0,2,4],[1,3,5],[4,0,2],[2,4,1]],progression:[0,1,2,3],pulse:[1,0,0,1,0],form:[.68,.72,.8,.64],strategy:"orbital",voices:voice("glass-harmonica","cello","choir","frame-drum",.78,{lead:{attack:.22,release:1.2,pan:0,vibrato:.001},counter:{instrument:"choir",attack:.5,release:1.4,pan:-.55},pulse:{gain:.02,release:.7},air:{instrument:"bowed-cymbal",gain:.018,pan:.62}})},
  sherlock_holmes:{identity:"Sherlock Holmes",root:38,bpm:96,meter:6,phraseBars:2,scale:[0,2,3,5,7,8,11],motif:[0,5,4,2,3,1],answer:[5,3,4,1,2,0],cadence:[4,2,1],rhythm:[.75,.25,1,.5,.5,2],chords:[[0,2,4],[3,5,1],[4,0,2],[0,2,4]],progression:[0,2,1,3],pulse:[1,0,0,1,0,0],form:[.4,.68,.94,.7],strategy:"chamber",voices:voice("solo-violin","bassoon","strings","woodblock",1.12,{lead:{pan:.4,attack:.065,vibrato:.0045},counter:{instrument:"clarinet",pan:-.5,gain:.034},pulse:{filter:2600,gain:.022,pan:0}})},
  neuromancer:{identity:"Neuromancer",root:31,bpm:132,meter:4,phraseBars:4,scale:[0,2,3,5,7,8,10],motif:[0,0,4,3,6,5,3,2],answer:[6,3,5,2,4,1,2,0],cadence:[5,2,0],rhythm:[.5,.5,.5,.5,1,.5,.5,2],chords:[[0,2,4],[5,0,2],[3,5,1],[4,1,3]],progression:[0,1,2,0,3,2],pulse:[1,0,1,0,1,0,1,0],form:[.5,.74,1,.78],strategy:"signals",voices:voice("electric-cello","synth-bass","analog-strings","gated-snare",.68,{pad:{attack:.72,release:2.4,pan:-.45,filter:1650,gain:.047},bass:{attack:.008,decay:.2,sustain:.44,release:.28,gain:.15,filter:720},lead:{attack:.028,release:.42,filter:3300},counter:{instrument:"electric-cello",pan:.6,filter:2600,gain:.034},pulse:{attack:.003,decay:.09,sustain:.04,release:.46,pan:-.25,gain:.062,filter:3600},air:{instrument:"bowed-cymbal",gain:.014,pan:.68}})},
  the_matrix:{identity:"The Matrix",root:36,bpm:126,meter:4,phraseBars:4,scale:[0,1,3,5,7,8,10],motif:[0,0,4,2,0,5,4,2],answer:[6,3,1,4,2,0],cadence:[4,1,0],rhythm:[.5,.5,.5,.5,1,.5,.5,2],chords:[[0,2,4],[4,1,3],[3,5,1],[0,2,4]],progression:[0,1,2,1],pulse:[1,0,1,0,1,0,0,1],form:[.46,.7,.98,.64],strategy:"pursuit",voices:voice("string-ostinato","cello","low-brass","taiko",.92,{lead:{attack:.018,decay:.2,sustain:.34,release:.3,pan:.22},counter:{instrument:"strings",pan:-.65},pulse:{gain:.052,pan:.55},pad:{pan:-.32,attack:.28,release:1.1}})},
};
const ALIASES:Record<string,string>={analyst:"default",sensei:"chuck_norris",troll:"full_troll",the_computer:"hal9000",detective:"sherlock_holmes",sherlock:"sherlock_holmes",the_sprawl:"neuromancer",m4tr1x:"the_matrix",matrix:"the_matrix",trinity:"the_matrix",ninja:"default",bureaucrat:"default",strategist:"default"};
const scoreId=(name:string)=>ALIASES[name]??(SCORE_BIBLES[name]?name:"default");
const clamp=(n:number,a:number,b:number)=>Math.min(b,Math.max(a,n));
const hz=(m:number)=>440*Math.pow(2,(m-69)/12);

class Random {
  private state:number;
  constructor(state:number){this.state=state||0x9e3779b9}
  next(){let x=this.state|0;x^=x<<13;x^=x>>>17;x^=x<<5;this.state=x;return(x>>>0)/4294967296}
  chance(p:number){return this.next()<p}
  pick<T>(xs:readonly T[]){return xs[Math.floor(this.next()*xs.length)]!}
}
const seedFor=(base:number,text:string,cycle:number)=>{let h=(base^cycle*0x9e3779b9)>>>0;for(const c of text)h=Math.imul(h^c.charCodeAt(0),16777619)>>>0;return h};
const midi=(s:ThemeScore,d:number,oct=0)=>{const n=s.scale.length,w=((d%n)+n)%n;return s.root+oct*12+s.scale[w]!+Math.floor(d/n)*12};

/** Pure deterministic planner; synthesis never changes compositional choices. */
export function planMusic(character:string,seed=1,cycle=0,phase:MusicPhase="idle"):MusicEvent[]{
  const id=scoreId(character),s=SCORE_BIBLES[id]!,r=new Random(seedFor(seed,id,cycle));
  const beat=60/s.bpm,events:MusicEvent[]=[]; let bar=0,at=0;
  for(let section=0;section<s.form.length;section++){
    const bars=s.phraseBars,level=s.form[section]!;
    for(let pb=0;pb<bars;pb++,bar++){
      const chordIndex=s.progression[bar%s.progression.length]!;
      const chord=s.chords[(chordIndex+(cycle>0&&pb===bars-2&&r.chance(.32)?1:0))%s.chords.length]!;
      const barDuration=s.meter*beat;
      for(const d of chord.slice(0,level>.82?3:2))events.push({at,duration:barDuration*.96,midi:midi(s,d),gain:level,role:"pad"});
      events.push({at,duration:beat*1.6,midi:midi(s,chord[0]!,-1),gain:level,role:"bass"});
      if(level>.65)events.push({at:at+barDuration/2,duration:beat*.8,midi:midi(s,chord[1]!,-1),gain:level*.78,role:"bass"});
      const source=pb===bars-1?s.cadence:pb>=Math.ceil(bars/2)?s.answer:s.motif;
      const motif=section===2?[...source].reverse():source;
      let cursor=at+(section===1?beat*.5:0),i=0;
      while(cursor<at+barDuration-beat*.2){
        let degree=motif[i%motif.length]!;
        if(cycle>0&&!((pb===bars-1)&&(i>=motif.length-2))&&r.chance(.18))degree+=r.pick([-1,1]);
        const units=s.rhythm[i%s.rhythm.length]!,duration=beat*units;
        const protectedCadence=pb===bars-1&&cursor>=at+barDuration-beat*2;
        const stopTime=s.strategy==="stop-time"&&pb%2===1&&cursor>at+barDuration-beat;
        if(!stopTime&&(protectedCadence||r.chance(phase==="caution"?.55:phase==="investigating"?.9:.76)))
          events.push({at:cursor,duration:duration*.82,midi:midi(s,degree,section===2?2:1),gain:level,role:"lead"});
        const counterEntry=s.strategy==="chamber"?i%3===1:s.strategy==="signals"?i%4===0:s.strategy==="orbital"?i%5===0:section===2&&i%2===0;
        if(counterEntry)events.push({at:cursor+beat*(s.strategy==="signals"?.55:.28),duration:duration*(s.strategy==="orbital"?1.4:.68),midi:midi(s,degree+(s.strategy==="crooked"?3:2),1),gain:level*.62,role:"counter"});
        cursor+=duration;i++;
      }
      for(let p=0;p<s.meter*2;p++)if(s.pulse[p%s.pulse.length]){
        const dropout=s.strategy==="pursuit"&&section===1&&p>=s.meter;
        if(!dropout)events.push({at:at+p*beat/2,duration:beat*(s.strategy==="orbital"?.42:id==="neuromancer"?.2:.12),midi:midi(s,chord[0]!,-2),gain:level,role:"pulse",noise:id!=="hal9000"});
      }
      if(r.chance(id==="hal9000"?.55:id==="neuromancer"?.42:.16))events.push({at,duration:barDuration*.9,midi:midi(s,chord[2]??chord[0]!),gain:level,role:"air",noise:id==="neuromancer"});
      at+=barDuration;
    }
  }
  return events.sort((a,b)=>a.at-b.at||a.role.localeCompare(b.role));
}

/**
 * A compact, theme-derived acknowledgement layered over the running score.
 * These events carry no analytical meaning and never start audio on their own.
 */
export function planMusicalAccent(character:string,accent:MusicalAccent):MusicEvent[]{
  const s=SCORE_BIBLES[scoreId(character)]!;
  if(accent==="badge"){
    const opening=s.motif[0]??0,middle=s.motif[1]??2;
    return [
      {at:0,duration:.34,midi:midi(s,opening,1),gain:.28,role:"counter"},
      {at:.2,duration:.42,midi:midi(s,Math.max(opening+1,middle),1),gain:.32,role:"lead"},
      {at:.48,duration:.78,midi:midi(s,s.scale.length,1),gain:.38,role:"lead"},
    ];
  }
  const approach=s.cadence.at(-2)??2;
  return [
    {at:0,duration:.48,midi:midi(s,approach,1),gain:.22,role:"counter"},
    {at:.3,duration:.72,midi:midi(s,s.scale.length,1),gain:.3,role:"lead"},
  ];
}

export class FlowMusicEngine {
  private context=new AudioContext(); private master=this.context.createGain(); private mix=this.context.createGain();
  private timer=0; private cursor=0; private cycle=0; private generation=0; private phase:MusicPhase="idle";
  private active=new Map<AudioScheduledSourceNode,AudioNode[]>(); private waves=new Map<Instrument,PeriodicWave>(); private noiseBuffers=new Map<Instrument,AudioBuffer>();
  private stopped=false; private starting=false; private baseSeed:number; private lastAccentAt=-Infinity;
  private id:string; private requestedId:string; private timeline:MusicEvent[]=[]; private timelineDuration=0; private origin=0; private volume:number;
  constructor(character:string,volume:number,seed?:number){
    this.id=scoreId(character);this.requestedId=this.id;this.volume=volume;this.baseSeed=seed??globalThis.crypto.getRandomValues(new Uint32Array(1))[0]!;
    const comp=this.context.createDynamicsCompressor();comp.threshold.value=-22;comp.knee.value=18;comp.ratio.value=8;comp.attack.value=.012;comp.release.value=.3;
    const reverb=this.context.createConvolver(),wet=this.context.createGain(),dry=this.context.createGain();
    const frames=Math.floor(this.context.sampleRate*2.4),impulse=this.context.createBuffer(2,frames,this.context.sampleRate),random=new Random(0x51a7cafe);
    for(let channel=0;channel<2;channel++){const data=impulse.getChannelData(channel);for(let i=0;i<frames;i++){const decay=Math.pow(1-i/frames,2.8);data[i]=(random.next()*2-1)*decay*(i<90?i/90:1)}}
    reverb.buffer=impulse;wet.gain.value=.18;dry.gain.value=.92;
    this.mix.connect(dry);dry.connect(comp);this.mix.connect(reverb);reverb.connect(wet);wet.connect(comp);comp.connect(this.master);this.master.connect(this.context.destination);this.master.gain.value=0;
  }
  start(){
    if(this.timer||this.stopped||this.starting)return;this.starting=true;
    void this.context.resume().then(()=>{
      if(this.stopped)return;const now=this.context.currentTime;this.origin=now+.12;this.replan();
      this.master.gain.cancelScheduledValues(now);this.master.gain.setValueAtTime(0,now);this.master.gain.linearRampToValueAtTime(this.target(),this.origin+.7);
      this.timer=window.setInterval(()=>this.schedule(),100);this.starting=false;this.schedule();
    }).catch(()=>{this.starting=false});
  }
  setVolume(v:number){this.volume=v;this.hold(this.context.currentTime);this.master.gain.setTargetAtTime(this.target(),this.context.currentTime,.12)}
  setPhase(p:MusicPhase){if(p!==this.phase){this.phase=p;this.replanFromNextCycle()}}
  accent(kind:MusicalAccent){
    if(this.stopped||!this.timer||this.context.state!=="running")return;
    const now=this.context.currentTime;if(now-this.lastAccentAt<1.4)return;this.lastAccentAt=now;
    for(const event of planMusicalAccent(this.id,kind))this.render(event,now+.045+event.at);
  }
  setCharacter(character:string){
    const next=scoreId(character);this.requestedId=next;const token=++this.generation;if(this.stopped)return;const now=this.context.currentTime;
    if(next===this.id){this.hold(now);this.master.gain.linearRampToValueAtTime(this.target(),now+.3);return}
    this.hold(now);this.master.gain.linearRampToValueAtTime(0,now+.5);
    window.setTimeout(()=>{if(this.stopped||token!==this.generation||next!==this.requestedId)return;this.disposeActive();this.id=next;this.cycle=0;this.origin=this.context.currentTime+.12;this.replan();this.master.gain.setValueAtTime(0,this.context.currentTime);this.master.gain.linearRampToValueAtTime(this.target(),this.context.currentTime+.75);this.schedule()},540);
  }
  async stop(){if(this.stopped)return;this.stopped=true;++this.generation;window.clearInterval(this.timer);this.timer=0;this.hold(this.context.currentTime);this.master.gain.linearRampToValueAtTime(0,this.context.currentTime+.5);await new Promise(r=>window.setTimeout(r,560));this.disposeActive();await this.context.close()}
  private target(){return clamp(this.volume,0,100)/100*.28}
  private hold(at:number){if(this.master.gain.cancelAndHoldAtTime)this.master.gain.cancelAndHoldAtTime(at);else{const v=this.master.gain.value;this.master.gain.cancelScheduledValues(at);this.master.gain.setValueAtTime(v,at)}}
  private replan(){this.timeline=planMusic(this.id,this.baseSeed,this.cycle,this.phase);this.timelineDuration=Math.max(...this.timeline.map(event=>event.at+event.duration));this.cursor=0}
  private replanFromNextCycle(){/* phase remains explicit and takes effect at the next musical return */}
  private schedule(){
    const now=this.context.currentTime,horizon=now+1.4;
    while(!this.stopped){
      if(this.cursor>=this.timeline.length){if(this.origin+this.timelineDuration>horizon)return;this.origin+=this.timelineDuration;++this.cycle;this.replan();continue}
      const event=this.timeline[this.cursor]!,plannedAt=this.origin+event.at;if(plannedAt>horizon)return;
      const at=Math.max(plannedAt,now+.04);const elapsed=Math.max(0,at-plannedAt);this.cursor++;
      if(elapsed<event.duration+SCORE_BIBLES[this.id]!.voices[event.role].release)this.render(event,at,Math.max(.03,event.duration-elapsed));
    }
  }
  private render(e:MusicEvent,at:number,duration=e.duration){
    const spec=SCORE_BIBLES[this.id]!.voices[e.role],level=spec.gain*e.gain;
    if(e.noise&&e.role==="pulse"){this.renderPercussion(e,spec,at,level);return}
    const osc=this.context.createOscillator();osc.setPeriodicWave(this.periodicWave(spec.instrument));
    const frequency=hz(e.midi);osc.frequency.setValueAtTime(frequency,at);
    if(spec.vibrato>0&&duration>.35)osc.frequency.setValueCurveAtTime(new Float32Array([frequency,frequency*(1+spec.vibrato),frequency,frequency*(1-spec.vibrato),frequency]),at,duration);
    this.wire(osc,spec,at,duration,level);
  }
  private periodicWave(instrument:Instrument){
    const cached=this.waves.get(instrument);if(cached)return cached;const partials=this.partials(instrument),real=new Float32Array(partials.length),imag=new Float32Array(partials.length);
    for(let i=1;i<partials.length;i++)imag[i]=partials[i]!;const wave=this.context.createPeriodicWave(real,imag,{disableNormalization:false});this.waves.set(instrument,wave);return wave;
  }
  private partials(instrument:Instrument):readonly number[]{
    const profiles:Record<Instrument,readonly number[]>={
      strings:[0,1,.48,.3,.19,.12,.08,.05],cello:[0,1,.55,.3,.16,.1,.06],piano:[0,1,.62,.34,.2,.11,.07,.04],
      "french-horn":[0,1,.28,.46,.24,.14,.07],"low-brass":[0,1,.38,.52,.25,.12,.06],"solo-violin":[0,1,.58,.37,.24,.16,.1,.06],
      bassoon:[0,1,.2,.55,.16,.32,.08],clarinet:[0,1,.03,.62,.02,.34,.01,.18],choir:[0,1,.35,.18,.3,.12,.16,.07],
      "glass-harmonica":[0,1,.08,.42,.05,.24,.04,.16],harp:[0,1,.5,.26,.14,.08,.04],"electric-cello":[0,1,.52,.28,.2,.13,.08],
      "baritone-guitar":[0,1,.68,.38,.24,.15,.09,.05],"pizzicato-strings":[0,1,.42,.24,.13,.07,.04],"analog-strings":[0,1,.36,.31,.2,.14,.09,.06],
      "synth-bass":[0,1,.74,.24,.12,.06,.03],"gated-snare":[0,1,.5,.32,.2,.13,.08],"string-ostinato":[0,1,.62,.4,.27,.17,.1,.06],
      timpani:[0,1,.12,.05],taiko:[0,1,.2,.08],"frame-drum":[0,1,.1,.04],woodblock:[0,1,.35,.16],"bowed-cymbal":[0,1,.18,.31,.12,.24,.1],air:[0,1,.12,.04],
    };return profiles[instrument];
  }
  private renderPercussion(e:MusicEvent,spec:Voice,at:number,level:number){
    const duration=Math.min(e.duration,spec.instrument==="gated-snare"?.46:spec.instrument==="timpani"||spec.instrument==="taiko"?.32:.12),src=this.context.createBufferSource();src.buffer=this.noiseBuffer(spec.instrument);src.playbackRate.value=.96+new Random(seedFor(this.baseSeed,this.id+e.role,Math.floor(e.at*1000)+this.cycle)).next()*.08;this.wire(src,spec,at,duration,level*(spec.instrument==="gated-snare"?.42:.2));
    if(["timpani","taiko","frame-drum"].includes(spec.instrument)){const body=this.context.createOscillator();body.type="sine";const base=hz(e.midi);body.frequency.setValueAtTime(base*1.35,at);body.frequency.exponentialRampToValueAtTime(Math.max(35,base*.72),at+duration);this.wire(body,{...spec,attack:.003,decay:.08,sustain:.04,release:.18},at,duration,level*.8)}
  }
  private noiseBuffer(instrument:Instrument){
    const cached=this.noiseBuffers.get(instrument);if(cached)return cached;const frames=Math.ceil(this.context.sampleRate*.6),buffer=this.context.createBuffer(1,frames,this.context.sampleRate),data=buffer.getChannelData(0),r=new Random(seedFor(0x7069766f,instrument,1));
    for(let i=0;i<frames;i++){const t=i/this.context.sampleRate,decay=Math.exp(-t*(instrument==="gated-snare"?7:instrument==="taiko"?12:24));const gate=instrument==="gated-snare"&&t>.34?Math.max(0,1-(t-.34)*30):1;data[i]=(r.next()*2-1)*decay*gate*(instrument==="woodblock"?.18:.42)}this.noiseBuffers.set(instrument,buffer);return buffer;
  }
  private wire(source:AudioScheduledSourceNode,spec:Voice,at:number,duration:number,level:number){
    const filter=this.context.createBiquadFilter(),env=this.context.createGain(),pan=this.context.createStereoPanner();filter.type="lowpass";filter.frequency.value=spec.filter;pan.pan.value=spec.pan;
    const releaseStart=at+Math.max(.025,duration),peak=Math.min(releaseStart-.012,at+Math.max(.006,Math.min(spec.attack,duration*.3))),decayEnd=Math.min(releaseStart-.006,peak+spec.decay),floor=.0001,sustain=Math.max(.0002,level*spec.sustain);
    env.gain.setValueAtTime(floor,at);env.gain.exponentialRampToValueAtTime(Math.max(.0002,level),peak);env.gain.exponentialRampToValueAtTime(sustain,Math.max(peak+.002,decayEnd));env.gain.setValueAtTime(sustain,releaseStart);env.gain.exponentialRampToValueAtTime(floor,releaseStart+Math.max(.04,spec.release));
    source.connect(filter);filter.connect(env);env.connect(pan);pan.connect(this.mix);const nodes:AudioNode[]=[filter,env,pan];this.active.set(source,nodes);source.addEventListener("ended",()=>{this.active.delete(source);for(const node of nodes)try{node.disconnect()}catch{}},{once:true});source.start(at);source.stop(releaseStart+Math.max(.04,spec.release)+.06);
  }
  private disposeActive(){for(const [source,nodes] of this.active){try{source.stop()}catch{}for(const node of nodes)try{node.disconnect()}catch{}}this.active.clear()}
}
