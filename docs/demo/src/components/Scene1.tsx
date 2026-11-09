import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { COLORS, mono, SAFE } from "../theme";
import { TerminalCard } from "./primitives";

/**
 * Scene 1: the problem. A plain MEMORY.md where the old belief is selected and
 * deleted, then one word is typed over it. Context is gone.
 */
export const Scene1: React.FC<{ duration: number }> = ({ duration }) => {
  const frame = useCurrentFrame();

  const selStart = 26;
  const selEnd = 54;
  const delStart = 58;
  const delEnd = 74;
  const typeStart = 86;
  const typeEnd = 122;

  const sel = interpolate(frame, [selStart, selStart + 8, selEnd, selEnd + 6], [0, 1, 1, 0], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
  });
  const del = interpolate(frame, [delStart, delEnd], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const typedCount = interpolate(frame, [typeStart, typeEnd], [0, 10], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const typed = "Fly.io".slice(0, Math.round(typedCount));

  const cursorOn = Math.floor(frame / 15) % 2 === 0;

  return (
    <AbsoluteFill style={{ background: COLORS.bg, padding: "0 120px" }}>
      <div style={{ position: "absolute", top: 96, left: 120, right: 120 }}>
        <div style={{ fontFamily: mono, fontSize: 15, color: COLORS.dimmer, letterSpacing: 3, marginBottom: 18 }}>
          THE PROBLEM
        </div>
        <div style={{ fontFamily: mono, fontSize: 46, color: COLORS.text, lineHeight: 1.25, fontWeight: 500 }}>
          Agent memory is a document.
        </div>
      </div>

      <div style={{ position: "absolute", top: 250, left: 120, right: 120, bottom: SAFE.cardFloor + 40 }}>
        <TerminalCard title="~/.hermes/MEMORY.md" accent={COLORS.dim} badge={
          <div style={{ fontFamily: mono, fontSize: 13, color: COLORS.dimmer }}>plain text</div>
        }>
          <div style={{ opacity: 0.45, fontSize: 19, lineHeight: 1.9, color: COLORS.dim }}>
            # memory
          </div>
          <div
            style={{
              position: "relative",
              display: "inline-block",
              marginTop: 8,
              padding: "2px 6px",
              marginLeft: -6,
              borderRadius: 4,
              background: `rgba(245,158,11,${0.26 * sel})`,
              outline: sel > 0.04 ? `1px solid rgba(245,158,11,${0.7 * sel})` : "none",
            }}
          >
            <span
              style={{
                fontSize: 21,
                color: COLORS.text,
                opacity: del > 0.02 ? del : 1,
                textDecoration: sel > 0.6 && del > 0.5 ? "line-through" : "none",
                textDecorationColor: COLORS.amber,
                whiteSpace: "pre",
              }}
            >
              The user ships on Vercel.
            </span>
          </div>

          <div style={{ marginTop: 12, fontSize: 21, lineHeight: 1.7, whiteSpace: "pre" }}>
            <span style={{ color: COLORS.text }}>The user ships on </span>
            <span style={{ color: COLORS.emerald, fontWeight: 500 }}>{typed}</span>
            <span style={{ color: COLORS.emerald, opacity: cursorOn ? 1 : 0 }}>|</span>
          </div>

          <div
            style={{
              marginTop: 26,
              paddingTop: 18,
              borderTop: `1px solid ${COLORS.border}`,
              opacity: interpolate(frame, [delEnd + 10, delEnd + 26], [0, 1], {
                extrapolateLeft: "clamp", extrapolateRight: "clamp",
              }),
            }}
          >
            <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
              <div style={{ width: 8, height: 8, borderRadius: 99, background: COLORS.red }} />
              <div style={{ fontFamily: mono, fontSize: 18, color: COLORS.red }}>
                Previous belief deleted. No record that Vercel was ever the answer.
              </div>
            </div>
          </div>
        </TerminalCard>
      </div>
    </AbsoluteFill>
  );
};
