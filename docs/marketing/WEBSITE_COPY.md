# Ready website copy for www.jarocki.org

Status: proposed copy only; this file does not publish or modify the website.
The HTML fragment below matches the existing **Open tooling** section in the
reviewed website snapshot. Check the selected release's public status before
adding it. The longer Markdown description remains available below.

## HTML row for the existing Open tooling section

Insert this single row inside the existing `<div class="rows">` beneath
**Open tooling**, alongside go-roast and nucleotide. It uses the site's existing
`row`, `key`, and `val` classes; no stylesheet or framework change is required.
The fragment links to the repository without claiming v1.0 approval, production
integration qualification, or measured learning gains.

```html
<div class="row">
  <span class="key">Pivotglass</span>
  <span class="val"><strong><a href="https://github.com/jarocki/pivotglass">From a clue to a defensible judgment</a></strong>Local, AI-augmented threat-investigation workspace. Frame investigative questions, collect deliberately, inspect sourced relationships and provenance, compare explanations, and report findings with uncertainty visible. Guided question framing and a synthetic offline case support analyst practice; models can explain or propose, while analysts retain judgment and review authority.</span>
</div>
```

The existing page calls this section instrumentation built, forked, or modified
by the maintainer. This row describes Pivotglass's investigative purpose while
fitting that established project-list structure. It is ready to review and paste;
no external publication was performed.

---

## Pivotglass

![Pivotglass Digital Looking Glass wordmark](https://raw.githubusercontent.com/jarocki/pivotglass/main/docs/brand/pivotglass-looking-glass-v1.png)

[Watch the short Overview](https://github.com/jarocki/pivotglass/blob/main/docs/media/series-v1.0.0/pivotglass-overview-v1.0.0.mp4)

### From a clue to a defensible judgment

Pivotglass is a local, AI-augmented workspace for cyber-threat investigation.
It connects the question an analyst is trying to answer with the evidence,
sources, competing explanations, and report that support the judgment.

An alert or a suspicious indicator starts the work. Pivotglass helps an analyst
ask what happened, inspect which sources support the explanation, consider
alternatives, and decide which observation would change the assessment.

### Work through the investigation

1. **Frame the question.** Use a Pursuit Brief and, when useful, guided Novice
   Q&A to identify the decision, scope, available data, and unknowns.
2. **Collect deliberately.** Select collection actions, review document
   candidates, and retain source and parser receipts.
3. **Inspect connections.** Read relationship graphs and provenance history
   with the edge basis visible. A shared property alone does not prove common
   control.
4. **Test explanations.** Record hypotheses, predictions, contradictions,
   gaps, and structured analytic technique results.
5. **Explain the judgment.** Produce a report and structured export that
   another analyst can inspect.

### Learn while doing the work

New analysts can practice question framing and reflection in a synthetic
offline case and during later investigations. Experienced analysts can choose
lighter guidance. Mentoring and demonstrated analytical competence still
matter: Pivotglass does not certify expertise or claim measured learning gains.

### Start locally, connect intentionally

The browser cockpit runs locally by default. The offline learning case needs
no API key or provider account. Enabled collection and model services may
receive information selected for their requests; review data-handling rules
before connecting them. Capacity and integration maturity are documented.

The v1.0.0 release includes implementation, infrastructure, and operations
guidance alongside the user guide. The stable scope is the bounded local
analyst workspace; integrations and additional intake formats remain preview
or deferred as documented.

- [Explore the repository](https://github.com/jarocki/pivotglass)
- [Install and run](https://github.com/jarocki/pivotglass/blob/main/docs/QUICKSTART.md)
- [Complete the offline case](https://github.com/jarocki/pivotglass/blob/main/docs/LEARNING_WORKSPACE.md)
- [Read the user guide](https://github.com/jarocki/pivotglass/blob/main/docs/USER_GUIDE.md)
- [Review data handling](https://github.com/jarocki/pivotglass/blob/main/docs/DATA_SAFETY.md)
- [Plan implementation](https://github.com/jarocki/pivotglass/blob/main/docs/operations/IMPLEMENTATION.md)

Maintainer: John Jarocki. Project license: MIT; third-party dependency licenses
are documented separately in release trust materials.
