# Pivotglass video series — v1.0.0

Four distinct edits with actual synthetic-case UI captures, Descript’s Jesse neural voice, original Pivotglass generative music, and captions. These are review candidates for tone and pace; they are edited capture montages rather than continuous click recordings.

| Film | Purpose | Duration | Resources |
|---|---|---:|---|
| [Through the Digital Looking Glass](pivotglass-overview-v1.0.0.mp4) | Overview | 1:16 | [Captions](pivotglass-overview-v1.0.0.vtt) · [Transcript](pivotglass-overview-v1.0.0-transcript.md) · [Edit manifest](pivotglass-overview-v1.0.0.json) |
| [Analyst Walkthrough: From Question to Handoff](pivotglass-analyst-v1.0.0.mp4) | Analyst | 2:06 | [Captions](pivotglass-analyst-v1.0.0.vtt) · [Transcript](pivotglass-analyst-v1.0.0-transcript.md) · [Edit manifest](pivotglass-analyst-v1.0.0.json) |
| [PIVOT Glass: One Indicator, New Perspectives](pivotglass-pivot-v1.0.0.mp4) | Pivot | 1:24 | [Captions](pivotglass-pivot-v1.0.0.vtt) · [Transcript](pivotglass-pivot-v1.0.0-transcript.md) · [Edit manifest](pivotglass-pivot-v1.0.0.json) |
| [Visualize, Challenge, Report](pivotglass-visualization-v1.0.0.mp4) | Visualization | 1:49 | [Captions](pivotglass-visualization-v1.0.0.vtt) · [Transcript](pivotglass-visualization-v1.0.0-transcript.md) · [Edit manifest](pivotglass-visualization-v1.0.0.json) |

## Production and analytical boundaries

- **Overview:** brisk invitation, all twelve evidence views, original Nightgrid electronic/new wave score.
- **Analyst:** question framing, unknowns, admission, evidence links, ACH, SAT, coverage and handoff; quieter Ambient EDM.
- **PIVOT Glass:** file → domain → IP and URL, provenance, analyst grouping and a discriminating collection question; original Code Rain pursuit score.
- **Visualization/reporting:** the twelve views, exact data, ACH overlap, Key Assumptions Check findings and Markdown/PDF handoff; restrained Ambient EDM.

Music is generated through the existing `pivotglass.core.music` composition and synthesis engine. Section density follows the edit chapters and sidechain compression lowers music under speech. No commercial movie score or artist recording is used. Inspect the four score JSON files for the actual note events.

Descript stock voice synthesis exposes no excitement or wonder control. The curious scripts, faster pitch-preserving playback, visual rhythm and music shape the tone; subjective listening review remains necessary. The provider supplies one-second aligned transcript groups. Caption and screenshot switches use those real groups, adjusted for playback speed, rather than claiming precise word alignment.

The training case is synthetic and offline. The Key Assumptions Check is an agent-authored exercise recorded through operator commands. It remains **pending analyst disposition**: completion checks required fields, not correctness or attribution. Empty activity charts are shown as empty. Graph position, grouping, coverage similarity and Dossier completeness are not actor attribution or danger scores.

The report now retains structured technique inputs and outputs alongside the real disposition. Fenced authored JSON is escaped with a sufficiently long Markdown fence; rendering does not alter the ledger.

## Review and reproduce

Open [the caption-enabled player](index.html) through a local HTTP server, as described in [Quick Start](../../QUICKSTART.md#watch-with-captions). A server with byte-range support is needed for reliable seeking. Captions are enabled by default; separate Markdown transcripts provide the same narration.

The public production plan, narration timing, source captures, scores and manifests are checked in. Private Descript audio exports and signed download links are not published. To reproduce, provide the four exported M4A files (`overview`, `analyst`, `pivot`, `visualization`) in a private audio directory:

```bash
.venv/bin/python scripts/render_video_series.py \
  --audio-dir /path/to/private/descript-exports \
  --timing docs/media/series-v1.0.0/narration-timing.json \
  --work-dir /tmp/pivotglass-series-render
```

Requires FFmpeg and the repository Python environment. The renderer never synthesizes speech or contacts a provider. Prior approved [five-minute tour](../pivotglass-guided-demo-v1.0.0.mp4) is preserved as the earlier edit.

[Logo and brand concept](../../brand/README.md) · [User Guide](../../USER_GUIDE.md)
