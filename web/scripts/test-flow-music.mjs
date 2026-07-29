import assert from "node:assert/strict";
import { planMusic, SCORE_BIBLES } from "../app/flow-music.ts";

const modes = ["default", "chuck_norris", "full_troll", "hal9000", "sherlock_holmes", "neuromancer", "the_matrix"];
const signature = (events) => JSON.stringify(events.map(({ at, duration, midi, role, noise }) => [at, duration, midi, role, !!noise]));

const timelines = modes.map((mode) => planMusic(mode, 0x51c0ffee, 0));
assert.equal(new Set(timelines.map(signature)).size, modes.length, "all public modes need distinct timelines");
assert.equal(new Set(modes.map((mode) => SCORE_BIBLES[mode].strategy)).size, modes.length, "orchestration strategies must be unique");
assert.equal(new Set(modes.map((mode) => JSON.stringify(SCORE_BIBLES[mode].voices))).size, modes.length, "role articulation and spatial contracts must be unique");
const acousticInstruments = new Set(["strings","cello","piano","french-horn","low-brass","solo-violin","bassoon","clarinet","choir","glass-harmonica","harp","electric-cello","timpani","taiko","frame-drum","woodblock","bowed-cymbal","air"]);
for (const mode of modes) for (const voice of Object.values(SCORE_BIBLES[mode].voices)) {
  assert.ok(acousticInstruments.has(voice.instrument), `${mode} must use an orchestral/atmospheric instrument model, got ${voice.instrument}`);
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
}

console.log(`flow-music: ${modes.length} deterministic, rhythmically distinct score planners verified`);
