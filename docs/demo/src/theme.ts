import { loadFont } from "@remotion/google-fonts/JetBrainsMono";

export const mono = loadFont("normal", {
  weights: ["400", "500", "700"],
  subsets: ["latin"],
}).fontFamily;

export const COLORS = {
  bg: "#070809",
  card: "#0f1113",
  cardAlt: "#131619",
  border: "rgba(255,255,255,0.08)",
  borderStrong: "rgba(255,255,255,0.14)",
  text: "#e8eaed",
  dim: "#8b9099",
  dimmer: "#5c616b",
  emerald: "#10b981",
  emeraldDim: "rgba(16,185,129,0.12)",
  cyan: "#22d3ee",
  cyanDim: "rgba(34,211,238,0.12)",
  violet: "#a78bfa",
  violetDim: "rgba(167,139,250,0.12)",
  amber: "#f59e0b",
  amberDim: "rgba(245,158,11,0.12)",
  red: "#ef4444",
  redDim: "rgba(239,68,68,0.12)",
};

// Safe zones: subtitles sit at bottom 36px, all cards must stay above bottom 110px.
export const SAFE = { subtitleBottom: 36, cardFloor: 110 };
