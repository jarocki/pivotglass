"use client";

import { useEffect, useState, type CSSProperties, type ReactNode } from "react";
import { createPortal } from "react-dom";

type AdvisorCategory =
  | "investigation"
  | "dossier"
  | "visualization"
  | "challenge"
  | "attention"
  | "configuration";

type VoiceProfile = {
  rate: number;
  pitch: number;
  hints: readonly string[];
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

const VOICE_PROFILES: Readonly<Record<string, VoiceProfile>> = {
  default: { rate: 1, pitch: 1, hints: ["samantha", "alex", "ava"] },
  chuck_norris: { rate: .92, pitch: .72, hints: ["aaron", "fred", "daniel", "thomas"] },
  hal9000: { rate: .78, pitch: .68, hints: ["alex", "daniel", "reed", "ralph"] },
  troll: { rate: 1.18, pitch: 1.16, hints: ["samantha", "ava", "victoria", "zoe"] },
  sherlock_holmes: { rate: .96, pitch: .88, hints: ["daniel", "oliver", "arthur", "jamie"] },
  neuromancer: { rate: 1.06, pitch: .78, hints: ["reed", "aaron", "alex", "daniel"] },
  the_matrix: { rate: .9, pitch: .82, hints: ["daniel", "aaron", "alex", "reed"] },
};

export function advisorIdentity(character: string): string {
  return ALIASES[character] ?? character;
}

export function AdvisorPortal({ children, style }: { children: ReactNode; style: CSSProperties }) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  if (!mounted) return null;
  return createPortal(<div className="advisor-portal" style={style}>{children}</div>, document.body);
}

function CharacterMark({ identity }: { identity: string }) {
  if (identity === "chuck_norris") return <><path d="M11 31 18 16h28l7 15-7 16H18Z"/><path d="m32 20 3.5 7 7.5 1-5.5 5 1.5 8-7-4-7 4 1.5-8-5.5-5 7.5-1Z"/></>;
  if (identity === "hal9000") return <><circle cx="32" cy="32" r="21"/><circle cx="32" cy="32" r="13"/><circle cx="32" cy="32" r="5" className="advisor-mark-solid"/><path d="M32 11v8M32 45v8M11 32h8M45 32h8"/></>;
  if (identity === "troll") return <><path d="M14 23q18-19 36 0v22q-18 13-36 0Z"/><path d="m20 29 8 4-9 3M44 29l-8 4 9 3M23 44q9 6 18 0"/><circle cx="25" cy="34" r="2" className="advisor-mark-solid"/><circle cx="39" cy="34" r="2" className="advisor-mark-solid"/></>;
  if (identity === "sherlock_holmes") return <><circle cx="27" cy="27" r="14"/><path d="m37 38 14 14M18 16q9-8 18 0M15 18h24M23 27h8M29 33q-5 4-9 0"/></>;
  if (identity === "neuromancer") return <><path d="M9 50V30l9-7v27M18 50V14l12 8v28M30 50V10l11 10v30M41 50V27l13-7v30"/><path d="M7 50h50M12 34h3M22 28h4M34 18h3M45 35h5"/></>;
  if (identity === "the_matrix") return <><path d="M17 50q-5-17 7-23-8-17 0-18 8 8 8 18 0-10 8-18 8 1 0 18 12 6 7 23Z"/><path d="M24 34h4M36 34h4M27 43q5 4 10 0"/></>;
  return <><circle cx="32" cy="32" r="21"/><path d="M32 15v34M15 32h34M21 21l22 22M43 21 21 43"/><circle cx="32" cy="32" r="6" className="advisor-mark-solid"/></>;
}

function TopicMark({ category }: { category: AdvisorCategory }) {
  const glyph: Record<AdvisorCategory, string> = {
    investigation: "◎",
    dossier: "◇",
    visualization: "⌁",
    challenge: "★",
    attention: "!",
    configuration: "⚙",
  };
  return <text x="51" y="56" className="advisor-topic-mark">{glyph[category]}</text>;
}

export function CharacterAdvisorArtwork({
  character,
  category,
  label,
}: {
  character: string;
  category: AdvisorCategory;
  label: string;
}) {
  const identity = advisorIdentity(character);
  return (
    <svg className={`advisor-art advisor-art-${identity}`} viewBox="0 0 64 64" role="img" aria-label={label}>
      <g className="advisor-character-mark"><CharacterMark identity={identity}/></g>
      <TopicMark category={category}/>
    </svg>
  );
}

export function speakCharacterNarration(character: string, message: string): boolean {
  if (typeof window === "undefined" || !("speechSynthesis" in window) || !("SpeechSynthesisUtterance" in window)) return false;
  const identity = advisorIdentity(character);
  const profile = VOICE_PROFILES[identity] ?? VOICE_PROFILES.default;
  const utterance = new SpeechSynthesisUtterance(message.replaceAll("`", ""));
  const voices = window.speechSynthesis.getVoices();
  const preferred = voices.filter((voice) => voice.localService !== false && voice.lang.toLowerCase().startsWith("en"));
  const available = preferred.length > 0 ? preferred : voices.filter((voice) => voice.lang.toLowerCase().startsWith("en"));
  utterance.voice = profile.hints
    .map((hint) => available.find((voice) => voice.name.toLowerCase().includes(hint)))
    .find((voice): voice is SpeechSynthesisVoice => Boolean(voice)) ?? available[0] ?? null;
  utterance.lang = utterance.voice?.lang ?? "en-US";
  utterance.rate = profile.rate;
  utterance.pitch = profile.pitch;
  utterance.volume = .88;
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(utterance);
  return true;
}

export function stopCharacterNarration() {
  if (typeof window !== "undefined" && "speechSynthesis" in window) window.speechSynthesis.cancel();
}
