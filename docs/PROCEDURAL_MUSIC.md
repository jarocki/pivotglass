# Procedural music design note

The terminal soundtrack originally rendered every character from one shared
motif, form, rhythm, and sine-wave arrangement, changing mainly the frequency
palette. It was deterministic and operationally safe, but its characters could
not carry distinct musical points of view.

The revised engine treats musical identity as inspectable score data. Each
character now has its own motif, scale, rhythm, bass motion, meter, tempo,
articulation, counterpoint behavior, pulse, and instrumental roles. A score
planner turns that identity into a four-act form—establish, disturb, pursue,
return—using motif rotation, inversion, fragmentation, imitation, phrase
breaths, harmonic motion, and an intentional release. A separate renderer then
synthesizes those events with role-specific spectra and envelopes.

This boundary matters: future changes can test composition independently from
audio encoding and playback. Character differentiation must remain audible in
the event timeline, not depend on color-like timbre swaps or hidden randomness.
The same mode, duration, volume, cycle/seed, and engine version remain
byte-deterministic.

The music remains presentation, never evidence. It may observe a bounded,
persisted-state transition solely to time an optional acknowledgement; it does
not interpret investigation events or assign them musical meaning. It starts
muted, is generated locally, carries no operational meaning, and may fail
without affecting the terminal or analytical workflow. The score uses original
high-level craft—motivic development, counterpoint, lyrical pacing, layered
tension, and theatrical timbre—without copying identifiable music.

Validation covers file format, duration, determinism, distinct character event
plans, phrase transformation, dynamic headroom, non-silence, and fallback
behavior. Automated checks establish structure and safety; listening remains
necessary for aesthetic judgment.

## Cinematic acoustic rendering

Reference recordings may refine a character through transferable properties
such as pacing, density, dramatic arc, register, and orchestral weight. They
never become source audio, melody templates, sampled fragments, or close
arrangements. The current public scores deliberately replace synthetic
computer voices with modeled acoustic and atmospheric ensembles:

- Default (Analyst): piano, cello, strings, and timpani;
- Chuck Norris: French horn calls, baritone guitar, strings, and impact timpani;
- Troll: bassoon, pizzicato strings, muted strings, and crooked woodblock;
- HAL9000: glass harmonica, cello, choir, and frame drum;
- Sherlock Holmes: solo violin, bassoon, chamber strings, and woodblock;
- Neuromancer: electric cello, synth bass, analog strings, and a gated darkwave
  backbeat; and
- The Matrix: string ostinato, low strings, brass choir, and syncopated taiko.

Each source is an original performance assembled from changing motifs,
counterlines, harmonic fields, bass motion, percussion, and atmospheric
layers. Additive harmonic profiles, expressive attacks and releases, gentle
vibrato, stereo placement, and an algorithmic room response make those roles
read as an ensemble rather than isolated beeps. Variation happens at both the
phrase and whole-form level, so subsequent movements develop the material
instead of replaying one short loop.

This is still a small, deterministic local synthesizer—not a recording of a
studio orchestra or a multi-gigabyte sampled instrument library. That
constraint keeps playback private, immediate, reproducible, and network-free.
It also means listening tests remain the authority for aesthetic quality, and
the timbre model should continue to evolve when it does not convincingly serve
the character.

## Operator continuity and gain

Theme changes preserve the operator's music choice. If music is enabled, the
controller safely stops the current player, renders the newly selected theme,
and resumes playback; if music is muted, the new theme remains muted. Ordinary
commands are no-ops because the controller ignores unchanged theme names.

Rendered tracks are peak-normalized before the operator volume is applied.
Volume 100 reaches approximately 30,000 on the signed 16-bit scale, leaving
headroom below clipping while making the maximum setting genuinely loud.
Lower settings remain linear, so volume 20 renders at one fifth of that peak.

## Adaptive acknowledgements

Pivotglass may add one small musical acknowledgement when authoritative state
shows that a new badge was awarded or a Dossier facet changed to filled. A
badge transforms the active character's motif into a quiet three-note arrival;
a completed facet receives a still quieter two-note harmonic resolution. The
gesture inherits the current ensemble, layers into the existing score, and
ends in about one second. It is not a generic success sound.

Initial state hydration and workspace changes reset the comparison baseline,
so pre-existing progress does not play a false celebration. If one update
contains both milestones, the badge gesture takes precedence, and a cooldown
prevents rapid updates from stacking cues. Muted music remains silent: an
acknowledgement never starts audio or changes the saved music preference.

These gestures react only to persisted counts and facet states. They do not
interpret evidence, imply confidence, announce a verdict, or modify the
investigation. The response is presentation layered after the authoritative
state transition.
