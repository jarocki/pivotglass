import assert from "node:assert/strict";
import { planMusic, planMusicalAccent, SCORE_BIBLES } from "../app/flow-music.ts";

const modes = ["default", "chuck_norris", "full_troll", "hal9000", "sherlock_holmes", "neuromancer", "the_matrix"];
const signature = (events) => JSON.stringify(events.map(({ at, duration, midi, role, noise }) => [at, duration, midi, role, !!noise]));

const timelines = modes.map((mode) => planMusic(mode, 0x51c0ffee, 0));
assert.equal(new Set(timelines.map(signature)).size, modes.length, "all public modes need distinct timelines");
assert.equal(new Set(modes.map((mode) => SCORE_BIBLES[mode].strategy)).size, modes.length, "orchestration strategies must be unique");
assert.equal(new Set(modes.map((mode) => JSON.stringify(SCORE_BIBLES[mode].voices))).size, modes.length, "role articulation and spatial contracts must be unique");
const acousticInstruments = new Set(["strings","cello","piano","french-horn","low-brass","solo-violin","bassoon","clarinet","choir","glass-harmonica","harp","electric-cello","timpani","taiko","frame-drum","woodblock","bowed-cymbal","air","baritone-guitar","pizzicato-strings","analog-strings","synth-bass","gated-snare","string-ostinato"]);
for (const mode of modes) for (const voice of Object.values(SCORE_BIBLES[mode].voices)) {
  assert.ok(acousticInstruments.has(voice.instrument), `${mode} must use an orchestral/atmospheric instrument model, got ${voice.instrument}`);
}
const expectedEnsembles = {
  default: ["piano", "cello", "strings", "timpani"],
  chuck_norris: ["french-horn", "baritone-guitar", "strings", "timpani"],
  full_troll: ["bassoon", "pizzicato-strings", "strings", "woodblock"],
  hal9000: ["glass-harmonica", "cello", "choir", "frame-drum"],
  sherlock_holmes: ["solo-violin", "bassoon", "strings", "woodblock"],
  neuromancer: ["electric-cello", "synth-bass", "analog-strings", "gated-snare"],
  the_matrix: ["string-ostinato", "cello", "low-brass", "taiko"],
};
for (const mode of modes) {
  const voices = SCORE_BIBLES[mode].voices;
  assert.deepEqual(
    [voices.lead.instrument, voices.bass.instrument, voices.pad.instrument, voices.pulse.instrument],
    expectedEnsembles[mode],
    `${mode} characteristic ensemble drift`,
  );
}
for (let index = 0; index < modes.length; index += 1) {
  const mode = modes[index];
  assert.equal(signature(timelines[index]), signature(planMusic(mode, 0x51c0ffee, 0)), `${mode} must reproduce`);
  assert.notEqual(signature(timelines[index]), signature(planMusic(mode, 0x51c0ffee, 1)), `${mode} needs macro variation`);
  const leads = timelines[index].filter((event) => event.role === "lead");
  const gaps = leads.slice(1).map((event, leadIndex) => Number((event.at - leads[leadIndex].at).toFixed(4)));
  assert.ok(new Set(gaps).size > 2, `${mode} must perform a rhythm, not a fixed onset grid`);
  const peakEstimate = timelines[index].reduce((peak, event, eventIndex, all) => {
    const level = all.filter((candidate) => candidate.at <= event.at && candidate.at + candidate.duration >= event.at)
      .reduce((sum, candidate) => sum + SCORE_BIBLES[mode].voices[candidate.role].gain * candidate.gain, 0);
    return Math.max(peak, level);
  }, 0);
  assert.ok(peakEstimate < 0.9, `${mode} dry mix needs headroom before compression (${peakEstimate})`);
}

const aliases = { sensei: "chuck_norris", the_computer: "hal9000", detective: "sherlock_holmes", the_sprawl: "neuromancer", m4tr1x: "the_matrix" };
for (const [alias, publicMode] of Object.entries(aliases)) {
  assert.equal(signature(planMusic(alias, 77, 0)), signature(planMusic(publicMode, 77, 0)), `${alias} compatibility drift`);
  for (const accent of ["badge", "dossier"]) {
    assert.equal(signature(planMusicalAccent(alias, accent)), signature(planMusicalAccent(publicMode, accent)), `${alias} ${accent} accent drift`);
  }
}

for (const mode of modes) {
  const badge = planMusicalAccent(mode, "badge");
  const dossier = planMusicalAccent(mode, "dossier");
  assert.equal(badge.length, 3, `${mode} badge acknowledgement must remain compact`);
  assert.equal(dossier.length, 2, `${mode} dossier acknowledgement must remain compact`);
  for (const event of [...badge, ...dossier]) {
    assert.ok(["lead", "counter"].includes(event.role), `${mode} accents must use pitched theme voices`);
    assert.equal(event.noise, undefined, `${mode} accents must not become notification percussion`);
    assert.ok(event.gain <= 0.38, `${mode} accents must remain beneath the principal score voice`);
    assert.ok(event.at + event.duration <= 1.3, `${mode} accents must resolve quickly`);
  }
}
assert.equal(new Set(modes.map((mode) => signature(planMusicalAccent(mode, "badge")))).size, modes.length, "badge acknowledgements must retain character identity");
assert.equal(new Set(modes.map((mode) => signature(planMusicalAccent(mode, "dossier")))).size, modes.length, "dossier acknowledgements must retain character identity");

console.log(`flow-music: ${modes.length} deterministic score planners and restrained adaptive accents verified`);
