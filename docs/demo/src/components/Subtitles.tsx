import React from "react";
import { AbsoluteFill, useCurrentFrame, interpolate } from "remotion";
import { COLORS, mono, SAFE } from "../theme";

export type Cue = [string, number]; // [text, startSeconds]

/**
 * Bottom-anchored subtitles. Fixed at SAFE.subtitleBottom so they never collide
 * with cards, which are all held above SAFE.cardFloor.
 */
export const Subtitles: React.FC<{ cues: Cue[]; durationSeconds: number }> = ({ cues, durationSeconds }) => {
  const frame = useCurrentFrame();
  const t = frame / 60;

  const active = cues.findIndex((c, i) => {
    const next = cues[i + 1]?.[1] ?? durationSeconds;
    return t >= c[1] && t < next;
  });

  if (active === -1) {
    const last = cues.length - 1;
    const start = cues[last][1];
    if (t < start) return null;
    return <Cue text={cues[last][0]} localFrame={frame - start * 60} fadeInOnly />;
  }

  const [text, start] = cues[active];
  return <Cue text={text} localFrame={frame - start * 60} />;
};

const Cue: React.FC<{ text: string; localFrame: number; fadeInOnly?: boolean }> = ({ text, localFrame }) => {
  const opacity = interpolate(localFrame, [0, 7], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const y = interpolate(localFrame, [0, 7], [6, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      <div
        style={{
          position: "absolute",
          bottom: SAFE.subtitleBottom,
          left: 0,
          right: 0,
          display: "flex",
          justifyContent: "center",
          opacity,
          transform: `translateY(${y}px)`,
        }}
      >
        <div
          style={{
            fontFamily: mono,
            fontSize: 27,
            lineHeight: 1.4,
            color: "#f2f4f6",
            textAlign: "center",
            padding: "9px 24px",
            borderRadius: 10,
            background: "rgba(7,8,9,0.86)",
            border: `1px solid ${COLORS.border}`,
            maxWidth: 1400,
            textShadow: "0 2px 12px rgba(0,0,0,0.9)",
            letterSpacing: 0.1,
          }}
        >
          {text}
        </div>
      </div>
    </AbsoluteFill>
  );
};
