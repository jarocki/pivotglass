# Visualization guide

Pivotglass visualizations exist to shorten the distance between an analyst's
question and a defensible next decision. They do not decorate the cockpit, add
analytical certainty, or turn proximity into a relationship.

## How to use this document

The question-to-view policy below describes supported intent families and their
analytical guardrails. It is not a promise of an arbitrary chart builder or a
complete implementation of every interaction mentioned in the design references.
Available views depend on the workspace fields and bounded intent builders.
The [visual analysis walkthrough](analysis/VISUALIZATIONS.md) explains delivered
views with a synthetic release screenshot and worked reading examples.

## Selection rules

Pivotglass applies these rules in order:

1. **Start with the question.** Select a visual family only after the analyst
   question and available fields are known.
2. **Show the evidence.** State the workspace scope, record count, missing-data
   behavior, uncertainty, and provenance limits alongside the view.
3. **Use the simplest effective geometry.** Prefer position and length for
   precise comparison. Use area, angle, color, motion, and three-dimensional
   effects only when they materially improve the task.
4. **Make color meaningful and redundant.** Sequential color communicates
   amount, diverging color communicates opposing directions, and qualitative
   color separates categories. Shape, text, or pattern repeats every important
   status.
5. **Keep exact data close.** Show accessible exact data alongside views.
   Review the selected export contract: a full workspace or graph export can
   have broader scope than the currently filtered or bounded plot.
6. **Explain the choice.** The selected view states **Why this fits** and
   **How to read it**. Hover and keyboard focus reveal compact-view details.
7. **Preserve uncertainty and missingness.** Pivotglass never silently imputes
   absent values, converts analytic confidence into probability, or treats an
   unassessed cell as neutral evidence.
8. **Use progressive disclosure.** The first scan shows the pattern. Selection
   opens evidence, caveats, provenance, and precise values without cluttering
   the overview.

## Question-to-view policy

| Analyst objective | Default view | Why it fits | Critical limit |
| --- | --- | --- | --- |
| Find days with concentrated activity | Calendar heatmap | Calendar position and intensity reveal bursts and quiet days quickly | UTC and zero-event days stay explicit |
| Find weak dimensions in one Dossier | Radar chart plus table | One bounded profile makes inward gaps visible across a common scale | One Dossier only; display scores are not confidence |
| Compare every indicator's investigation coverage | Compact Constellation matrix | Fixed rows and columns expose repeated gaps and uneven coverage in one scan | A peg is a coverage state, not a verdict |
| See current indicator-by-enrichment work | Lifecycle matrix | One cell preserves one authoritative job state at the intersection that matters | Color is repeated by shape, glyph, and text |
| Explore admitted entity relationships | Force-directed graph | Nodes and directional typed edges support path and neighborhood exploration | Spatial proximity never creates a relationship |
| Compare evidence against competing explanations | ACH matrix | The same evidence can be compared across every hypothesis, including contradiction | Unassessed is not neutral |
| See a numerical distribution | Histogram | Bins reveal shape, spread, clusters, and outliers without inventing order | Bin sensitivity and sample count stay visible |
| Compare numerical similarity or correlation | Scatter plot or PCA projection | Every point remains visible and spatial position supports cluster and outlier scanning | Similarity is not causation, relationship, or attribution |
| Follow a metric through ordered time | Line chart | Connected positions communicate ordered change efficiently | Missing values are not interpolated silently |
| Compare discrete evidence counts | Bar chart | Common baseline and bar length support accurate category comparison | Counts describe stored scope only |
| Understand parent-child structure | Dendrogram | Indentation and branching preserve hierarchy and path depth | Hierarchy does not imply support or causality |
| Read recorded likelihood ranges | Interval plot | Bounded bars show uncertainty without implying a single exact value | Confidence remains a separate assessment |

## Investigation Constellation

The Constellation uses a child's Lite Brite motif without asking the analyst to
decode a picture. It is intentionally dense:

- the indicator value remains the row label;
- all nine canonical Dossier dimensions remain aligned as columns;
- 18-pixel pegs keep many indicators in view;
- the matrix stays inside a bounded scroll window with sticky headings;
- a green check means coverage met, an amber half-circle means some evidence,
  an open circle means no evidence, and a dash means no automated path;
- readable dimension names replace cryptic abbreviations;
- source-labelled country flags describe the indicator's reported location,
  not attacker origin; unknown locations are left unflagged;
- a viewport-safe hover or keyboard-focus explainer provides the full dimension
  question, state meaning, and exact evidence count;
- one Tab enters the grid; arrow keys move between pegs, Home and End move to
  the first and last dimension, and Enter or Space pins a selection;
- selecting a peg pins the explanation below the matrix without moving rows, while selecting an indicator opens its
  evidence and provenance; and
- secondary filters are collapsed until needed, while search, sort, and the
  visible-row count stay immediately available.

Reading across answers, "Where are the gaps for this indicator?" Reading down
answers, "Which investigation dimension is repeatedly weak?"

**Filled** means the configured evidence-coverage threshold was met. It does
not mean the dimension's analytical question is proven, nor does it communicate
confidence, severity, or truth.

## Design references

The references in this section explain design choices and future guardrails.
References to external examples do not imply equivalent product capabilities.
Descriptions of scaling strategies, richer incident views, or additional chart
interactions are design guidance unless the current user guide demonstrates them.


### Interactive incident benchmark

Information is Beautiful's
[World's Biggest Data Breaches & Hacks](https://informationisbeautiful.net/visualizations/worlds-biggest-data-breaches-hacks/#bysensitivity)
is a useful model for dense incident exploration: preserve the overview, let
the analyst change the comparison lens, encode magnitude visibly, and reveal
the selected incident's story without removing its surrounding context. Its
data-sensitivity view is especially relevant to threat intelligence because it
turns an abstract impact category into a filterable comparison.

Pivotglass should apply that interaction pattern to incident, campaign, and
evidence-cluster views: overview first; explicit filters and encodings; details
on selection; and exact source data close at hand. Bubble size or spatial
proximity must never create or imply an entity relationship, confidence level,
or attribution.

## Reference review and Pivotglass decisions

| Reference | Strongest contribution | Pivotglass decision |
| --- | --- | --- |
| Stephen R. Midway, [Principles of Effective Data Visualization](https://doi.org/10.1016/j.patter.2020.100141) | Message-first design, appropriate geometry, meaningful color, uncertainty, small multiples, data/model separation, detailed captions, and outside review | Adopt as the primary design-quality checklist. Every view exposes its question, source scope, missingness, caveats, exact data, and reading guidance. |
| Financial Times Visual Vocabulary | Organizes charts by the question being asked: deviation, correlation, ranking, distribution, change, magnitude, part-to-whole, spatial, and flow | Adopt the question-first taxonomy. Do not expose a chart gallery as the analyst's starting point. |
| [Digital.gov](https://digital.gov/resources/an-introduction-to-data-visualization) | Begin with the research question; identify and clean sources; match chart to purpose and audience; check bias; design for accessibility; include enough metadata; test with users | Adopt as the workflow contract around the chart. A rendered graphic without provenance, plain language, accessible data, and feedback QA is incomplete. |
| [Appnovation's twelve principles](https://www.appnovation.com/blog/12-principles-data-visualization) | Clarity, simplicity, purpose, consistency, context, accuracy, encoding, intuitiveness, interaction, aesthetics, accessibility, and hierarchy | Adopt as presentation acceptance criteria. Treat aesthetics as useful only when accuracy and hierarchy already hold. |
| [Data Visualisation Catalogue](https://datavizcatalogue.com/) | Broad catalogue searchable by communication function, including comparison, proportion, relationship, hierarchy, location, distribution, range, time, process, and flow | Use for design discovery and vocabulary, not automatic selection. The catalogue itself notes that assigning charts to functions is imperfect. |
| [From Data to Viz](https://www.data-to-viz.com/) | Data-shape decision tree plus concrete caveats about ordering, truncated axes, spaghetti lines, histogram bins, hidden sample sizes, overplotting, rainbow scales, and counter-intuitive encodings | Encode the caveats as deterministic guardrails and QA cases. Use density or aggregation for large scatterplots; expose histogram bins; sort categorical comparisons; keep sample counts visible. |
| [GeeksforGeeks chart guide](https://www.geeksforgeeks.org/data-visualization/choosing-the-right-chart-type-a-technical-guide/) and [chart catalogue](https://www.geeksforgeeks.org/data-analysis/types-of-data-visualization/) | Accessible taxonomy of comparison, trend, relationship, distribution, composition, geographic, hierarchy, and flow charts | Use as a secondary terminology and completeness check. Do not inherit generic recommendations when stronger evidence warns against them—for example, radar, gauges, donuts, and bubbles require narrower conditions than the catalogue suggests. |
| [Datameer overview](https://www.datameer.com/blog/data-visualization/) | Practical framing around distributions, relationships, composition, and comparison; warning that oversimplification can erase important patterns; emphasis on clean, documented transformations | Adopt the data-shape framing and oversimplification warning. Do not use the page as a detailed encoding authority. |
| [Information is Beautiful: four elements](https://informationisbeautiful.net/visualizations/what-makes-a-good-data-visualization/) | A successful visual balances information integrity, function, visual form, and an interesting story | Adopt functional beauty and progressive storytelling. Story and character atmosphere may focus attention, but never replace provenance or change analytical meaning. |
| [Microsoft Flint](https://microsoft.github.io/flint-chart/) | A semantics-driven intermediate language that separates field meaning and chart intent from renderer-specific scales, axes, layout, and color | Keep semantic intent and deterministic compilation as the authority. Python chooses the supported analytical question and source data; Flint derives chart mechanics; the renderer only draws the validated result. |
| [VirusTotal Graph](https://docs.virustotal.com/docs/graph-documentation) | Entity-first relationship exploration with actual values, typed directional links, hover summaries, expansion, pinning, selection, labels, manual links, undo/redo, filtering, and export | Adopt the interaction vocabulary while preserving Pivotglass's stricter provenance boundary. Observed, derived-navigation, and manual assertion links remain visibly distinct. |

Repository policy and authoritative evidence remain controlling when any design
reference conflicts with analytical truthfulness or operator agency.

### Deliberate chart limits

- **Radar:** one Dossier on one common 0–100 coverage scale, always paired with
  a table. Never compare many dossiers or interpret area as confidence.
- **Bubble and packed-circle views:** use only when area encodes a documented
  magnitude and the layout does not imply relationships. Include a size legend.
- **Scatter and PCA:** show similarity or correlation only. At high density,
  switch to hexbin or two-dimensional density and preserve point-level access.
- **Network graph:** render stored relationships, conservative property pivots,
  and explicit analyst assertions or admission groups with distinct truth kinds
  and provenance. Spatial proximity and force-layout position are presentation.
- **Heatmap:** use for overview and pattern detection, with accessible exact
  values and a non-color status channel. Do not expect precise lookup by color.
- **Histogram:** expose count and adjustable bins; never hide zero-count or
  omitted entities silently.
- **Line and area:** cap simultaneous series, provide selection or small
  multiples beyond that cap, and avoid dual axes.
- **Geographic views:** use point or connection maps for actual locations.
  Choropleths require a defensible denominator and normalized rate; raw IoC
  counts by country do not qualify.
- **Sankey and flow:** require a measured quantity moving between stages. A
  Kill Chain sequence alone is not a quantitative flow.
- **Treemap and sunburst:** reserve for genuine containment hierarchies, not
  arbitrary graph neighborhoods.
- **Word clouds, gauges, donuts, decorative circular bars, and 3D charts:** do
  not use as analytical defaults. They trade comparison accuracy for novelty
  and rarely answer a Pivotglass question better than a table, bar, matrix, or
  interval view.

### Flint version boundary

Pivotglass pins `flint-chart` 0.4.0 for its qualified Chart.js intent paths.
Plotly and editable Office backends are not qualified product features merely
because the dependency contains them. Consult [Compatibility](COMPATIBILITY.md)
for the supported renderer boundary.
