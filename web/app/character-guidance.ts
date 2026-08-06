export type GuidanceAction = "focus" | "pane" | "command" | "alerts";

export type GuidanceCandidate = {
  category: "investigation" | "dossier" | "visualization" | "challenge" | "attention";
  idea: string;
  action: GuidanceAction;
  actionLabel: string;
  value: string;
};

export type CharacterGuidance = GuidanceCandidate & {
  characterName: string;
  message: string;
  contentClass: "narration";
  evidence: false;
};

const CHARACTER: Readonly<Record<string, { name: string; voice: readonly string[] }>> = {
  default: {
    name: "Default (Analyst)",
    voice: [
      "Analyst's note: {idea}",
      "The evidence suggests a practical next move: {idea}",
      "Before we widen the search, close one visible gap: {idea}",
      "Keep the hypothesis provisional and the next step testable: {idea}",
    ],
  },
  chuck_norris: {
    name: "Chuck Norris",
    voice: [
      "Chuck Norris already checked the blind spot. Your turn: {idea}",
      "A weak lead once tried to hide from Chuck Norris. {idea}",
      "Chuck Norris does not chase clues. Clues report for duty. {idea}",
      "The dossier has one round left in it: {idea}",
    ],
  },
  hal9000: {
    name: "HAL9000",
    voice: [
      "I have reviewed the board. {idea} I am sure this will go perfectly.",
      "A calm suggestion, before human improvisation begins: {idea}",
      "The mission remains entirely under control. The missing setting, less so: {idea}",
      "I would prefer not to repeat myself, so let us correct this cleanly: {idea}",
    ],
  },
  troll: {
    name: "Troll",
    voice: [
      "{idea} Or keep staring at the same pane. That seems productive. 🙄",
      "Tiny idea from the allegedly unhelpful one: {idea}",
      "Oh good, an avoidable blind spot. My favorite. {idea}",
      "The data left you a clue in plain sight. Rude of it, honestly: {idea}",
    ],
  },
  sherlock_holmes: {
    name: "Sherlock Holmes",
    voice: [
      "The board has made one fact rather conspicuous: {idea}",
      "Observe what is absent, not merely what is present. {idea}",
      "The commonplace detail is usually the one everyone neglects: {idea}",
      "A conclusion without its missing premise is merely theatre. Test this: {idea}",
    ],
  },
  neuromancer: {
    name: "Neuromancer",
    voice: [
      "A weak signal is blinking through the static: {idea}",
      "The sprawl keeps receipts. Jack into the next seam: {idea}",
      "Chrome rain on black glass; one route is still warm: {idea}",
      "The city buried the answer under traffic and old light. Cut through here: {idea}",
    ],
  },
  the_matrix: {
    name: "The Matrix",
    voice: [
      "The path is visible now: {idea}",
      "One connection changes the shape of the system. {idea}",
      "The pattern is not a prison once you can see its edges: {idea}",
      "Every system exposes a choice point. This is yours: {idea}",
    ],
  },
};

const ALIASES: Readonly<Record<string, string>> = {
  analyst: "default",
  bureaucrat: "default",
  strategist: "default",
  sensei: "chuck_norris",
  ninja: "chuck_norris",
  the_computer: "hal9000",
  full_troll: "troll",
  detective: "sherlock_holmes",
  the_sprawl: "neuromancer",
  m4tr1x: "the_matrix",
};

export function characterGuidance(
  character: string,
  candidates: readonly GuidanceCandidate[],
  sequence: number,
): CharacterGuidance | null {
  if (candidates.length === 0) return null;
  const identity = ALIASES[character] ?? character;
  const profile = CHARACTER[identity] ?? CHARACTER.default;
  const candidate = candidates[sequence % candidates.length];
  const template = profile.voice[Math.floor(sequence / candidates.length) % profile.voice.length];
  return {
    ...candidate,
    characterName: profile.name,
    message: template.replace("{idea}", candidate.idea),
    contentClass: "narration",
    evidence: false,
  };
}
