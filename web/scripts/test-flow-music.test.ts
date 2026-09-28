import assert from "node:assert/strict";
import test from "node:test";
import { planMusic, SCORE_BIBLES, musicEventTiming, musicCycleDuration } from "../app/flow-music.ts";

test("Code Rain plans dance percussion and character scores remain distinct", () => {
  const beat = 60 / SCORE_BIBLES.the_matrix.bpm;
  const firstBar = planMusic("m4tr1x").filter((event) => event.at < beat * 4);
  assert.deepEqual(firstBar.filter((event) => event.role === "pulse" && !event.drum).map((event) => Math.round(event.at / beat)), [0, 1, 2, 3]);
  assert.deepEqual(firstBar.filter((event) => event.drum === "snare").map((event) => event.at / beat), [1, 3]);
  assert.deepEqual(firstBar.filter((event) => event.drum === "hat").map((event) => event.at / beat), [.5, 1.5, 2.5, 3.5]);
  const signatures = ["default", "sensei", "full_troll", "the_computer", "detective", "the_sprawl", "m4tr1x"]
    .map((mode) => planMusic(mode).filter((event) => event.role === "lead").slice(0, 8).map((event) => [event.at, event.midi]));
  assert.equal(new Set(signatures.map((value) => JSON.stringify(value))).size, signatures.length);
});

test("Nightgrid uses dance percussion and Orbit leaves space between radar pings",()=>{
  const night=planMusic("the_sprawl");
  assert.ok(night.some(event=>event.drum==="snare"));
  assert.ok(night.some(event=>event.drum==="hat"));
  assert.equal(SCORE_BIBLES.neuromancer.voices.pulse.instrument,"electronic-kick");
  assert.equal(SCORE_BIBLES.the_matrix.voices.lead.instrument,"solo-violin");
  const orbit=planMusic("the_computer");
  assert.equal(orbit.filter(event=>event.role==="lead").length,4);
  assert.equal(orbit.filter(event=>event.role==="pulse").length,0);
  assert.deepEqual(orbit,planMusic("the_computer"));
});

test("Code Rain's fast string and glass parts lock to the drum grid across cycles",()=>{
  const s=SCORE_BIBLES.the_matrix,tick=60/s.bpm/4;
  for(const cycle of [0,1,3]){
    const events=planMusic("m4tr1x",17,cycle);
    for(const event of events)assert.ok(Math.abs(event.at/tick-Math.round(event.at/tick))<1e-8,`${event.role} at ${event.at}`);
    assert.ok(events.filter(e=>e.role==="lead").every(e=>e.midi>=55));
    assert.ok(events.filter(e=>e.role==="lead").length>70);
  }
  assert.equal(s.voices.counter.instrument,"glass-harp");
  assert.ok(SCORE_BIBLES.default.mixGain! < .42);
  assert.equal(SCORE_BIBLES.full_troll.voices.lead.instrument,"accordion");
});

test("a delayed scheduler never shifts or bunches rhythmic attacks, including the loop seam",()=>{
  const beat=60/SCORE_BIBLES.the_matrix.bpm;
  const hit={at:beat,duration:.1,midi:38,gain:1,role:"pulse" as const};
  assert.equal(musicEventTiming(hit,10,10+beat+.03),null);
  assert.deepEqual(musicEventTiming(hit,10,10),{at:10+beat,duration:.1});
  const duration=musicCycleDuration("m4tr1x");
  assert.ok(Math.abs(duration/beat-64)<1e-8);
  const first=planMusic("m4tr1x").find(e=>e.role==="pulse")!;
  assert.equal(musicEventTiming(first,10+duration,10+duration-.05)?.at,10+duration);
});

test("cinematic additions preserve the sparse Orbit and shared pursuit grid",()=>{
  const orbit=planMusic("the_computer",1,0);
  assert.equal(orbit.filter(e=>e.role==="counter").length,6);
  assert.equal(planMusic("the_computer",1,1).filter(e=>e.role==="counter").length,0);
  assert.equal(orbit.filter(e=>e.role==="pulse").length,0);
  assert.equal(SCORE_BIBLES.sherlock_holmes.voices.pad.instrument,"organ");
  assert.equal(SCORE_BIBLES.sherlock_holmes.voices.counter.instrument,"pub-piano");
  assert.ok(planMusic("sensei").some(e=>e.instrument==="taiko"));
  const rain=planMusic("m4tr1x");
  assert.ok(rain.some(e=>e.instrument==="solo-violin"&&e.duration>60/134*1.5));
});
