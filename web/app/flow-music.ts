export type MusicPhase = "idle" | "investigating" | "caution" | "complete";

type Voice = { offset: number; octave: number; gain: number; wave: OscillatorType; every: number };
type Score = { root: number; bpm: number; scale: number[]; motif: number[]; voices: Voice[] };

const SCORES: Record<string, Score> = {
  default: { root: 45, bpm: 72, scale: [0, 2, 3, 7, 9], motif: [0, 2, 4, 1, 3], voices: [{offset:0,octave:0,gain:.16,wave:"sine",every:8},{offset:0,octave:1,gain:.1,wave:"triangle",every:2},{offset:2,octave:2,gain:.06,wave:"sine",every:1}] },
  ninja: { root: 38, bpm: 58, scale: [0, 3, 5, 7, 10], motif: [0, 4, 1, 3, 2], voices: [{offset:0,octave:0,gain:.13,wave:"sine",every:12},{offset:0,octave:2,gain:.07,wave:"triangle",every:3}] },
  full_troll: { root: 43, bpm: 96, scale: [0, 2, 5, 7, 10], motif: [0, 3, 1, 4, 2, 1], voices: [{offset:0,octave:0,gain:.12,wave:"triangle",every:4},{offset:1,octave:1,gain:.07,wave:"square",every:2},{offset:3,octave:2,gain:.04,wave:"square",every:1}] },
  bureaucrat: { root: 41, bpm: 66, scale: [0, 2, 5, 7, 9], motif: [0, 1, 2, 1, 3, 2], voices: [{offset:0,octave:0,gain:.13,wave:"triangle",every:8},{offset:2,octave:1,gain:.07,wave:"sine",every:2}] },
  strategist: { root: 40, bpm: 64, scale: [0, 2, 3, 7, 8], motif: [0, 2, 1, 4, 3], voices: [{offset:0,octave:0,gain:.15,wave:"sine",every:8},{offset:2,octave:1,gain:.08,wave:"triangle",every:2},{offset:0,octave:2,gain:.04,wave:"sine",every:1}] },
  sensei: { root: 45, bpm: 78, scale: [0, 2, 5, 7, 9], motif: [0, 2, 4, 3, 1, 2], voices: [{offset:0,octave:0,gain:.14,wave:"sine",every:8},{offset:0,octave:1,gain:.08,wave:"triangle",every:2},{offset:2,octave:2,gain:.05,wave:"triangle",every:1}] },
  detective: { root: 38, bpm: 62, scale: [0, 3, 5, 8, 10], motif: [0, 2, 1, 4, 3], voices: [{offset:0,octave:0,gain:.15,wave:"sine",every:8},{offset:3,octave:1,gain:.07,wave:"triangle",every:3},{offset:1,octave:2,gain:.04,wave:"sine",every:2}] },
  the_computer: { root: 36, bpm: 84, scale: [0, 2, 4, 6, 9], motif: [0, 2, 4, 1, 3, 1], voices: [{offset:0,octave:0,gain:.13,wave:"sine",every:8},{offset:2,octave:1,gain:.07,wave:"triangle",every:2},{offset:4,octave:2,gain:.04,wave:"sine",every:1}] },
  the_sprawl: { root: 33, bpm: 56, scale: [0, 2, 5, 7, 10], motif: [0, 3, 2, 4, 1], voices: [{offset:0,octave:0,gain:.16,wave:"sawtooth",every:12},{offset:2,octave:1,gain:.06,wave:"sine",every:3},{offset:4,octave:2,gain:.035,wave:"triangle",every:2}] },
  m4tr1x: { root: 38, bpm: 88, scale: [0, 2, 3, 7, 10], motif: [0, 4, 2, 1, 3, 2], voices: [{offset:0,octave:0,gain:.12,wave:"sine",every:8},{offset:1,octave:1,gain:.07,wave:"triangle",every:2},{offset:3,octave:2,gain:.045,wave:"sine",every:1}] },
};

const hz = (midi: number) => 440 * Math.pow(2, (midi - 69) / 12);

/** Local, deterministic, phrase-based Web Audio transport. Music is presentation only. */
export class FlowMusicEngine {
  private context: AudioContext;
  private master: GainNode;
  private timer = 0;
  private next = 0;
  private step = 0;
  private score: Score;
  private phase: MusicPhase = "idle";

  constructor(character: string, volume: number) {
    this.context = new AudioContext();
    this.master = this.context.createGain();
    this.master.gain.value = volume / 1400;
    this.master.connect(this.context.destination);
    this.score = SCORES[character] ?? SCORES.default;
  }

  start() { this.next = this.context.currentTime + .05; this.timer = window.setInterval(() => this.schedule(), 25); this.schedule(); }
  setVolume(value: number) { this.master.gain.setTargetAtTime(value / 1400, this.context.currentTime, .12); }
  setPhase(phase: MusicPhase) { this.phase = phase; }
  async stop() { window.clearInterval(this.timer); this.master.gain.setTargetAtTime(0, this.context.currentTime, .04); await new Promise((resolve) => window.setTimeout(resolve, 120)); await this.context.close(); }

  private schedule() {
    const beat = 60 / this.score.bpm;
    while (this.next < this.context.currentTime + .22) {
      const barStep = this.step % 16;
      const density = this.phase === "investigating" ? 1 : this.phase === "caution" ? .55 : .75;
      for (const voice of this.score.voices) {
        if (barStep % voice.every !== 0 || ((this.step + voice.offset) % 7 === 6 && density < 1)) continue;
        const phrase = Math.floor(this.step / 16);
        const motifIndex = (Math.floor(this.step / voice.every) + voice.offset + phrase) % this.score.motif.length;
        const degree = this.score.motif[motifIndex];
        const cadence = this.phase === "complete" && barStep >= 12 ? 0 : degree;
        const midi = this.score.root + voice.octave * 12 + this.score.scale[cadence % this.score.scale.length];
        this.note(hz(midi), this.next, Math.min(beat * voice.every * .82, 3.8), voice.gain * density, voice.wave);
      }
      this.step += 1;
      this.next += beat / 2;
    }
  }

  private note(frequency: number, at: number, duration: number, level: number, wave: OscillatorType) {
    const oscillator = this.context.createOscillator(); const envelope = this.context.createGain();
    oscillator.type = wave; oscillator.frequency.setValueAtTime(frequency, at);
    envelope.gain.setValueAtTime(.0001, at); envelope.gain.exponentialRampToValueAtTime(level, at + .06);
    envelope.gain.exponentialRampToValueAtTime(.0001, at + duration);
    oscillator.connect(envelope); envelope.connect(this.master); oscillator.start(at); oscillator.stop(at + duration + .03);
  }
}
