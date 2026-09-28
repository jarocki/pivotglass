import assert from "node:assert/strict";
import test from "node:test";
import { draftQuestions, newCoachDraft, restoreCoachDraft } from "../app/question-coaching.ts";

test("unknowns generate collection questions without inventing a cause", () => {
  const draft = newCoachDraft();
  draft.answers = draft.answers.map(() => ({ text: "ignored retained text", unknown: true }));
  const questions = draftQuestions(draft.answers);
  assert.equal(questions.length, 3);
  assert.match(questions[0], /What happened/);
  assert.match(questions[1], /earliest event supported by evidence/);
  assert.match(questions[2], /competing explanations/);
  assert.ok(questions.every((q) => !q.includes("ignored retained text")));
});
test("reported context remains attributed and decisions require distinguishing evidence", () => {
  const answers = ["proxy log", "host beaconing", "email link", "host A on Tuesday", "contain host A", "approved test"].map((text) => ({ text, unknown: false }));
  const questions = draftQuestions(answers);
  assert.match(questions[0], /reported activity \(host beaconing\)/);
  assert.match(questions[0], /reported scope \(host A on Tuesday\)/);
  assert.match(questions[1], /only the earliest visible event/);
  assert.match(questions[2], /proposed alternative \(approved test\)/);
  assert.match(questions[2], /support the decision \(contain host A\)/);
  assert.match(questions[2], /proxy log/);
});
test("resuming retains edits, individual save receipts, reflection, and unknown answers", () => {
  const draft = newCoachDraft();
  draft.step = 6; draft.answers[2] = { text: "", unknown: true };
  draft.questions = ["Edited question?", "Second?", "Third?"]; draft.saved = [true, false, false];
  draft.reflection = "Need independent sources"; draft.completed = true;
  assert.deepEqual(restoreCoachDraft(JSON.stringify(draft)), draft);
});
test("malformed local drafts recover safely", () => {
  for (const raw of [null, "{", "null", '{"answers":[]}', JSON.stringify({ answers: [null, null, null, null, null, null] })]) {
    assert.deepEqual(restoreCoachDraft(raw), newCoachDraft());
  }
  const draft = newCoachDraft();
  assert.equal(restoreCoachDraft(JSON.stringify({ ...draft, step: 999, saved: ["false"] })).step, 6);
  assert.equal(restoreCoachDraft(JSON.stringify({ ...draft, saved: ["false"] })).saved[0], false);
});
