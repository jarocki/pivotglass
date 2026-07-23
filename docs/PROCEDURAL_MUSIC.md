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
The same mode, duration, volume, and engine version remain byte-deterministic.

The music remains presentation, never evidence. It consumes no investigation
events, starts muted, is generated locally, carries no operational meaning, and
may fail without affecting the terminal or analytical workflow. The score uses
original high-level craft—motivic development, counterpoint, lyrical pacing,
layered tension, and theatrical timbre—without copying identifiable music.

Validation covers file format, duration, determinism, distinct character event
plans, phrase transformation, dynamic headroom, non-silence, and fallback
behavior. Automated checks establish structure and safety; listening remains
necessary for aesthetic judgment.

## Sample-informed character refinement

Reference recordings may refine a character through transferable musical
properties without becoming source audio or a melody template. The first such
refinement maps the supplied `m4tr1x` reference's steady electronic pressure,
approximately 114–116 BPM motor, roughly 0.26-second attacks, dense bright
spectrum, narrow loudness range, and persistent low foundation into an original
minor-mode ostinato. Its declarative score now uses machine, sub-bass, and neon
roles with a continuous eighth-note drive. No recording is bundled, sampled,
streamed, or required at runtime.

The supplied Sensei reference takes the opposite path: restrained loudness,
long low drones, isolated swells, slow harmonic drift, and a gradual expansion
into brighter upper partials. Sensei now translates that spacious arc into an
original open-pitch language with earth, breath, bowl, and sparse gong roles,
long articulation, and no motoric beat. This keeps reflection and patient
attention at the center without reproducing the reference melody or recording.

The Sprawl reference begins as low infrastructure beneath descending spectral
staircases, layers irregular machine cycles, and opens into a broad noisy bloom
late in its form. The Sprawl now uses an original falling seven-note cell over
a seven-beat grid, fog and signal layers, an obscured tonal center, asymmetric
pulses, and a rising section-level tension curve. Its final act expands rather
than merely replaying the opening texture, while the loop boundary still fades
cleanly back into the buried city foundation.

The Ninja reference builds from sparse low-register gestures into a sudden,
high-contrast 140 BPM impact section with clipped attacks and dense broadband
rhythm. Ninja now uses an original stealth-to-reveal form: shadow bass, a thin
veil, short blade-like cells, measured footstep pulses, and a steep late tension
curve. Its opening withholds energy; its later sections expose the same compact
motif under pressure rather than borrowing the reference's melody or beat.

The Detective reference sets a quiet low-register feint before abruptly
revealing a crooked pulse, dry attacks, compact chromatic questions, and uneven
accent returns. The Detective now uses an original three-beat clue-and-footfall
grammar at roughly 72 BPM, with rain atmosphere, irregular knocks, terse motif
cells, and a sharp second-act reveal. The recognizable reference theme and its
specific arrangement are deliberately excluded.

The Computer reference sustains a calm two-level electronic pulse beneath
luminous suspended harmony, repeating arpeggiated motion, high spectral haze,
and an unusually narrow loudness range. The Computer now treats cyberspace as
dream rather than machinery: an original slow 64 BPM data current supports a
128 BPM orbit, star-like motif points, cloud harmony, and gently changing but
nearly level section intensity. No reference melody, vocal material, or exact
arrangement enters the score.

The Strategist reference is useful chiefly for long-range architecture: a
patient foundation, compact recurring material, purposeful layer entries,
widening register, and pressure accumulated toward a broad arrival. Strategist
now uses an original four-stage plan at 60 BPM, with sparse measure marks,
foundation bass, a restrained motif, horizon harmony, and a tension curve that
does not reveal its full weight until the final act. The reference progression,
melody, and orchestration are excluded.

The Default reference suggests quiet forward motion: a steady low foundation,
open consonant spacing, repeating arpeggiated breath, gradual register growth,
and hopeful lift without a hard dramatic turn. Default now uses an original
64 BPM field-and-sky grammar, with seed-like motif points, gentle stride,
open-pitch harmony, and a restrained upward tension curve. It serves as a
welcoming center rather than an absence of character, while excluding the
reference progression, melody, and orchestration.

## Operator continuity and gain

Theme changes preserve the operator's music choice. If music is enabled, the
controller safely stops the current player, renders the newly selected theme,
and resumes playback; if music is muted, the new theme remains muted. Ordinary
commands are no-ops because the controller ignores unchanged theme names.

Rendered tracks are peak-normalized before the operator volume is applied.
Volume 100 reaches approximately 30,000 on the signed 16-bit scale, leaving
headroom below clipping while making the maximum setting genuinely loud.
Lower settings remain linear, so volume 20 renders at one fifth of that peak.
