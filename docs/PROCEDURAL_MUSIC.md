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

The music remains presentation, never evidence. It consumes no investigation
events, starts muted, is generated locally, carries no operational meaning, and
may fail without affecting the terminal or analytical workflow. The score uses
original high-level craft—motivic development, counterpoint, lyrical pacing,
layered tension, and theatrical timbre—without copying identifiable music.

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
- Chuck Norris: French horn, low brass, strings, and timpani;
- Troll: bassoon, cello, muted strings, and woodblock;
- HAL9000: glass harmonica, cello, choir, and frame drum;
- Sherlock Holmes: solo violin, bassoon, chamber strings, and woodblock;
- Neuromancer: electric cello, contrabass, dark strings, and taiko; and
- The Matrix: string ostinato, low strings, brass choir, and taiko.

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
