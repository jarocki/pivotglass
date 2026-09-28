"use client";
import { useEffect, useRef, useState } from "react";
import { COACH_STEPS, PRACTICE_LESSONS, draftQuestions, newCoachDraft, restoreCoachDraft, type CoachDraft } from "./question-coaching";
import type { GuidanceLevel } from "./guidance-profile";

export function QuestionCoach({ workspace, level, onCommand }: {
  workspace: string; level: GuidanceLevel; onCommand: (command: string) => Promise<string>;
}) {
  const storageKey = `pivotglass.question-coach.v1:${encodeURIComponent(workspace)}`;
  const [draft, setDraft] = useState<CoachDraft>(newCoachDraft);
  const [ready, setReady] = useState(false);
  const [open, setOpen] = useState(level === "novice");
  const [practice, setPractice] = useState(0);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    try {
      setDraft(restoreCoachDraft(window.localStorage.getItem(storageKey)));
      const count = Number(window.localStorage.getItem("pivotglass.question-practice.v1"));
      setPractice(Number.isFinite(count) ? Math.max(0, Math.floor(count)) : 0);
    } catch { setNotice("Browser storage is unavailable. This session will remain in memory only."); }
    setReady(true);
  }, [storageKey]);
  useEffect(() => {
    if (!ready) return;
    try { window.localStorage.setItem(storageKey, JSON.stringify(draft)); }
    catch { setNotice("Draft could not be stored in this browser. Keep this page open to retain it."); }
  }, [draft, ready, storageKey]);
  const step = COACH_STEPS[draft.step];
  function move(next: number) {
    setDraft((current) => ({ ...current, step: next }));
    requestAnimationFrame(() => heading.current?.focus());
  }
  function updateAnswer(text: string, unknown: boolean) {
    const index = draft.step;
    setDraft((current) => ({ ...current, answers: current.answers.map((a, i) => i === index ? { text, unknown } : a) }));
  }
  function review() {
    setDraft((current) => ({ ...current, step: COACH_STEPS.length, questions: draftQuestions(current.answers), saved: [false, false, false] }));
    requestAnimationFrame(() => heading.current?.focus());
  }
  async function save(index: number) {
    setBusy(true); setNotice("");
    try {
      const receipt = await onCommand(`analysis question ${draft.questions[index].trim()}`);
      setDraft((current) => ({ ...current, saved: current.questions.map((_, i) => i === index || Boolean(current.saved[i])) }));
      setNotice(`${receipt}. Question ${index + 1} saved to the active investigation in ${workspace}.`);
    } catch (error) { setNotice(`Could not save: ${error instanceof Error ? error.message : String(error)}. Your draft is retained. Check the notebook before retrying if the response was interrupted.`); }
    finally { setBusy(false); }
  }
  function finishPractice() {
    const next = practice + 1;
    setPractice(next); setDraft((current) => ({ ...current, completed: true }));
    try { window.localStorage.setItem("pivotglass.question-practice.v1", String(next)); } catch { /* Session progress remains visible. */ }
    setNotice("Practice recorded locally. Revisit the saved question after collection: did the evidence answer it or change it?");
  }
  return <section className="question-coach" aria-label="Investigative question coaching">
    <header><div><span>ON-THE-JOB PRACTICE · {workspace}</span><h3>BUILD INVESTIGATIVE QUESTIONS TOGETHER</h3></div><button type="button" onClick={() => setOpen(!open)} aria-expanded={open}>{open ? "PAUSE Q&A" : "START / RESUME Q&A"}</button></header>
    {open && ready && <>
      <p>One question at a time. Your answers are context you report, pending source checks. Drafts stay in this browser for this workspace; only questions you explicitly save enter the notebook. No collection runs here.</p>
      <p className="coach-practice">{practice} framing practice session{practice === 1 ? "" : "s"} completed · {PRACTICE_LESSONS[practice % PRACTICE_LESSONS.length]}</p>
      {practice >= 3 && <small>Try framing the next question yourself, then use this Q&A to check your reasoning. Choose lighter guidance in Help when you feel ready. Practice counts do not certify expertise.</small>}
      {step ? <>
        <span>QUESTION {draft.step + 1} OF {COACH_STEPS.length}</span>
        <h4 ref={heading} tabIndex={-1}>{step.title}</h4><p>{step.lesson}</p>
        <label htmlFor="coach-answer">Your answer</label>
        <textarea key={`answer-${draft.step}`} id="coach-answer" maxLength={2000} value={draft.answers[draft.step].text} disabled={draft.answers[draft.step].unknown} placeholder={step.hint} onChange={(e) => updateAnswer(e.target.value, false)}/>
        <label className="coach-unknown"><input key={`unknown-${draft.step}`} type="checkbox" checked={draft.answers[draft.step].unknown} onChange={(e) => updateAnswer(draft.answers[draft.step].text, e.target.checked)}/>I DON&apos;T KNOW YET</label>
        {draft.answers[draft.step].unknown && <p>We will keep this as a knowledge gap. Later collection can help you answer it.</p>}
        <div className="coach-actions"><button type="button" disabled={draft.step === 0} onClick={() => move(draft.step - 1)}>BACK</button><button type="button" disabled={!draft.answers[draft.step].unknown && !draft.answers[draft.step].text.trim()} onClick={() => draft.step === COACH_STEPS.length - 1 ? review() : move(draft.step + 1)}>{draft.step === COACH_STEPS.length - 1 ? "REVIEW DRAFT QUESTIONS" : "NEXT QUESTION"}</button></div>
      </> : <>
        <h4 ref={heading} tabIndex={-1}>Review and edit your investigative questions</h4>
        <p>These are starting drafts, not findings. Check source, scope, uncertainty, and what evidence could change the answer. Save only useful questions to the active investigation.</p>
        <details><summary>REVIEW YOUR REPORTED CONTEXT</summary>{COACH_STEPS.map((s, i) => <p key={s.id}><b>{s.title}</b><br/>{draft.answers[i].unknown || !draft.answers[i].text.trim() ? "Not yet known" : draft.answers[i].text}</p>)}</details>
        {draft.questions.map((question, index) => <div className="coach-review" key={index}><label htmlFor={`coach-question-${index}`}>Draft question {index + 1}</label><textarea id={`coach-question-${index}`} value={question} maxLength={8000} disabled={busy || draft.saved[index]} onChange={(e) => setDraft((current) => ({ ...current, questions: current.questions.map((q, i) => i === index ? e.target.value : q) }))}/><button type="button" disabled={busy || draft.saved[index] || !question.trim()} onClick={() => void save(index)}>{draft.saved[index] ? "SAVED TO NOTEBOOK" : "SAVE THIS QUESTION"}</button></div>)}
        <label htmlFor="coach-reflection">Reflection: what did you learn, and what would change your mind?</label><textarea id="coach-reflection" maxLength={2000} value={draft.reflection} disabled={draft.completed} onChange={(e) => setDraft((current) => ({ ...current, reflection: e.target.value }))}/>
        <div className="coach-actions"><button type="button" disabled={busy || draft.saved.some(Boolean)} onClick={() => move(COACH_STEPS.length - 1)}>EDIT ANSWERS</button><button type="button" disabled={busy || draft.completed || !draft.saved.some(Boolean) || !draft.reflection.trim()} onClick={finishPractice}>{draft.completed ? "PRACTICE COMPLETED" : "COMPLETE PRACTICE"}</button></div>
        <small>Complete practice after saving at least one reviewed question and reflecting. Continue in the workbench: propose competing explanations, collect explicitly, then review evidence and revise.</small>
      </>}
      <details><summary>START A FRESH SESSION / CLEAR LOCAL DRAFT</summary><p>This clears the local Q&A draft and reflection. Saved notebook questions remain.</p><button type="button" disabled={busy} onClick={() => { setDraft(newCoachDraft()); setNotice(""); }}>CLEAR DRAFT AND START AGAIN</button></details>
    </>}
    {notice && <p role="status">{notice}</p>}
  </section>;
}
