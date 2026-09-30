# Pivotglass v1.0.0 guided demo — transcript

Edited actual browser captures from an isolated synthetic workspace, synchronized to Descript’s Jesse stock neural voice. This is not a continuous screen recording. No live enrichment or investigative model calls were used. Duration: **5:00.160**.

Chapter timing follows the generated speech. External captions use Descript transcript ticks at approximately five-second granularity; short adjacent cues are merged within chapters. They are not word-level alignment. A separate caption band preserves the interface. Owner listening review remains open.

## Reproduce the case

Run `python scripts/demo_workspace.py` from an installed checkout and follow the [offline quickstart](../QUICKSTART.md). The second document is [the synthetic admission fixture](../examples/demo-two-indicators.json). The [source captures and production notes](demo-v1.0.0-source/README.md) explain the edited demonstration.

## 00:00:00.000 — A question, not a verdict

![Actual captured interface](demo-v1.0.0-source/01-cockpit.png)

Welcome to Pivotglass version zero point nine point nine. This edited walkthrough uses real screens from an isolated, synthetic investigation. No live intelligence service or language model is required. The cockpit brings questions, evidence, alternative explanations, and analyst decisions into one workspace.

## 00:00:19.840 — Begin with what you have

![Actual captured interface](demo-v1.0.0-source/02-coach.png)

Novice mode starts with a conversation. What data do you have? What happened? The question coach helps a new analyst describe the source, the observed event, and the decision the investigation needs to support. Coaching is a practice aid, not a substitute for evidence.

## 00:00:36.880 — Make unknowns explicit

![Actual captured interface](demo-v1.0.0-source/03-unknown.png)

Do you know how it started? Here the analyst explicitly says no. That unknown remains visible. Useful analysis does not fill a missing origin story with a confident guess.

## 00:00:49.200 — Review before saving

![Actual captured interface](demo-v1.0.0-source/04-review.png)

The coach proposes investigative questions. The analyst edits a question to ask what independent evidence distinguishes common control from shared hosting. Saving is an explicit decision; a draft becomes a durable question only after review.

## 00:01:05.520 — Practice and reflection

![Actual captured interface](demo-v1.0.0-source/05-practice.png)

A short reflection records what the analyst practiced. Repeated work builds habits: state the decision, separate observations from assumptions, and identify evidence that could change the conclusion. Practice history records participation, not a certification of expertise.

## 00:01:24.000 — Challenge the favored explanation

![Actual captured interface](demo-v1.0.0-source/06-analysis.png)

The analytical workbench keeps competing hypotheses and contradictory evidence visible. Structured techniques help the analyst challenge a favored explanation. A contradiction is something to investigate and disposition, rather than hide to make a cleaner narrative.

## 00:01:40.640 — See coverage and gaps

![Actual captured interface](demo-v1.0.0-source/07-constellation.png)

The constellation is a navigation aid for the admitted evidence. It helps locate objects and gaps. Position and visual emphasis do not establish adversary ownership, confidence, or importance.

## 00:01:53.760 — Inspect the complete indicator

![Actual captured interface](demo-v1.0.0-source/08-indicator.png)

Open an indicator to inspect its complete value and stored relationships. In this synthetic case, a file communicates with a domain. A relationship supports a specific observation; it does not, by itself, establish common control.

## 00:02:09.680 — Follow the source trail

![Actual captured interface](demo-v1.0.0-source/09-provenance.png)

The detail view exposes provenance and collection history. Source identifiers, timestamps, response hashes, and conflicting results let another analyst examine where an observation came from. A model summary is not the original source.

## 00:02:25.520 — Preview before admission

![Actual captured interface](demo-v1.0.0-source/12-intake.png)

Local document intake first previews candidates. This synthetic document contains a domain and a deliberately long URL. The analyst selects both, then explicitly admits the source and candidates. Previewing alone does not add evidence to the workspace.

## 00:02:43.120 — Keep the admitted source

![Actual captured interface](demo-v1.0.0-source/13-library.png)

The source library retains the admitted document and its digest. After restarting the isolated service, the same source and admitted objects remain available. Keeping source material makes review and later correction possible.

## 00:02:57.360 — History records analyst decisions

![Actual captured interface](demo-v1.0.0-source/14-history.png)

Provenance history shows the actual workflow: document admission, creation of an analyst promotion group, and two candidate admissions. The branches record the analyst decision to promote these candidates together. They do not assert a shared adversary or an observed threat relationship.

## 00:03:15.280 — Distinguish relationships from grouping

![Actual captured interface](demo-v1.0.0-source/15-group-graph.png)

The relationship graph now shows seven nodes and five visible edges. Stored relationships use their own edge style; analyst grouping uses dotted yellow edges. The long URL wraps inside its label. The analyst can read the complete value and distinguish grouping from evidence.

## 00:03:33.840 — Explain the evidence connection

![Actual captured interface](demo-v1.0.0-source/17-link.png)

The analyst records an explicit evidence link with a rationale. Here, a synthetic observation supports the shared hosting alternative without establishing control. The ledger stores the link as an analyst judgment, preserving the observation and the competing hypothesis.

## 00:03:50.800 — Prepare a reviewable handoff

![Actual captured interface](demo-v1.0.0-source/16-report-current-normal.png)

Generate a deterministic report from the current workspace. The report retains the investigative questions, alternative explanations, explicit evidence links, unresolved contradictions, and next collection requirements. It is a handoff for review, not an automatic verdict. The analyst still checks the assessment, limitations, and handling before sharing. Choose Save Markdown for the complete editable report, or Print and Save PDF for a printable copy.

## 00:04:21.040 — Start locally; enable services deliberately

![Actual captured interface](demo-v1.0.0-source/18-config.png)

Configuration separates optional intelligence and model services from the local workflow. Enable providers deliberately and understand their network and data boundaries. The implementation and operations guides document prerequisites, backup, restore, maintenance, and failure recovery.

## 00:04:40.080 — Presentation stays separate from truth

![Actual captured interface](demo-v1.0.0-source/19-theme-named.png)

Personas and themes give the workspace a distinctive atmosphere. This is the Nightgrid presentation. Visuals and optional sound help the working experience; neither changes evidence or analytical authority. Start with the offline quickstart, then follow the user guide through a reviewed, defensible handoff.
