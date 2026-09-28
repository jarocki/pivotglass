export const COACH_STEPS = [
  { id: "data", title: "What data do you have?", lesson: "Start with provenance. A report is a source; its claims still need checking.", hint: "Name the report, logs, indicators, source, and collection time. Do not paste secrets." },
  { id: "event", title: "What happened?", lesson: "Separate what a source reports from what you suspect. Describe an observation before naming a cause.", hint: "For example: a proxy log records repeated connections; compromise is still a suspicion." },
  { id: "origin", title: "Do you know how it started?", lesson: "The first event you can see may not be the initial event. Unknown is a useful answer.", hint: "Give the earliest known event and its source, or choose I DON'T KNOW YET." },
  { id: "scope", title: "Who or what is affected, and when?", lesson: "Bound the question by systems, identities, indicators, and a time window. Avoid assuming every related node is affected.", hint: "State the scope and dates you can support, and what is still missing." },
  { id: "decision", title: "What decision must this investigation support?", lesson: "A useful question helps someone choose an action. Specify the decision without presuming the answer.", hint: "For example: decide whether to contain a host or collect more evidence." },
  { id: "alternative", title: "What else could explain this?", lesson: "Practice challenging your first explanation. Identify evidence that could distinguish it from an alternative.", hint: "Could this be expected administration, a test, or another cause? What would change your mind?" },
] as const;
export type CoachAnswer = { text: string; unknown: boolean };
export type CoachDraft = { step: number; answers: CoachAnswer[]; questions: string[]; saved: boolean[]; reflection: string; completed: boolean };
export function newCoachDraft(): CoachDraft {
  return { step: 0, answers: COACH_STEPS.map(() => ({ text: "", unknown: false })), questions: [], saved: [], reflection: "", completed: false };
}
export function restoreCoachDraft(raw: string | null): CoachDraft {
  try {
    const value = JSON.parse(raw ?? "null");
    if (!value || !Array.isArray(value.answers) || value.answers.length !== COACH_STEPS.length) return newCoachDraft();
    if (!value.answers.every((a: CoachAnswer) => typeof a?.text === "string" && typeof a.unknown === "boolean")) return newCoachDraft();
    return {
      step: Math.max(0, Math.min(COACH_STEPS.length, Number(value.step) || 0)),
      answers: value.answers.map((a: CoachAnswer) => ({ text: a.text.slice(0, 2000), unknown: a.unknown })),
      questions: Array.isArray(value.questions) ? value.questions.slice(0, 3).map((q: unknown) => typeof q === "string" ? q.slice(0, 8000) : "") : [],
      saved: Array.isArray(value.saved) ? value.saved.slice(0, 3).map((s: unknown) => s === true) : [],
      reflection: typeof value.reflection === "string" ? value.reflection.slice(0, 2000) : "", completed: value.completed === true,
    };
  } catch { return newCoachDraft(); }
}
export function draftQuestions(answers: CoachAnswer[]): string[] {
  const known = (index: number) => !answers[index]?.unknown && Boolean(answers[index]?.text.trim());
  const text = (index: number) => answers[index].text.trim().replace(/\s+/g, " ");
  const scope = known(3) ? ` Within the reported scope (${text(3)})` : " Within a scope and time window still to be established";
  return [
    known(1) ? `What evidence supports or contradicts the reported activity (${text(1)})?${scope}, what is observed and what remains an inference?` : "What happened, and which sourced observations can establish the activity, affected scope, and time window?",
    known(2) ? `Does the reported starting point (${text(2)}) represent the initial event or only the earliest visible event, and what evidence would distinguish them?` : "What is the earliest event supported by evidence, and what additional sources could establish how the activity started?",
    `Which evidence would distinguish ${known(5) ? `the proposed alternative (${text(5)}) from other explanations` : "competing explanations"}${known(4) ? ` to support the decision (${text(4)})` : " before choosing an investigative action"}?${known(0) ? ` What can the available sources (${text(0)}) establish, and what collection is still needed?` : " Which sources should be collected first, and why?"}`,
  ];
}
export const PRACTICE_LESSONS = [
  "Provenance: next time, check who collected a source, when, and whether it is independent of your other sources.",
  "Disconfirmation: next time, name a finding that would weaken your favored explanation before collecting more evidence.",
  "Scope: next time, compare the earliest visible event with the earliest possible event and explain the visibility gap.",
  "Decision: next time, define what evidence would justify action and what uncertainty would require more collection.",
];
