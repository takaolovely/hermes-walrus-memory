import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { COLORS, mono, SAFE } from "../theme";
import { TerminalCard, Line, Pill } from "./primitives";

/**
 * Scene 2: the ledger. Lines accumulate rather than replace. The citation pill
 * lands after the rule is derived.
 */
export const Scene2: React.FC<{ duration: number }> = ({ duration }) => {
  const frame = useCurrentFrame();

  const rows = [
    { at: 14, id: "obs#01", color: COLORS.cyan, text: "The user ships on Vercel.", tag: "observed" },
    { at: 74, id: "fix#02", color: COLORS.amber, text: "The user ships on Fly.io, Vercel for static.", tag: "corrected" },
    { at: 138, id: "fix#03", color: COLORS.amber, text: "The user ships on Fly.io first, Vercel for static.", tag: "refined" },
    { at: 206, id: "rule#04", color: COLORS.emerald, text: "Fly.io first, Vercel for static.", tag: "derived" },
  ];

  const citationAt = 270;
  const citationOpacity = interpolate(frame, [citationAt, citationAt + 14], [0, 1], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill style={{ background: COLORS.bg, padding: "0 120px" }}>
      <div style={{ position: "absolute", top: 74, left: 120, right: 120 }}>
        <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between" }}>
          <div>
            <div style={{ fontFamily: mono, fontSize: 15, color: COLORS.dimmer, letterSpacing: 3, marginBottom: 14 }}>
              APPEND-ONLY LEDGER
            </div>
            <div style={{ fontFamily: mono, fontSize: 42, color: COLORS.text, fontWeight: 500 }}>
              A correction is a new line.
            </div>
          </div>
          <Pill color={COLORS.cyan} bg={COLORS.cyanDim} delay={6}>
            nothing is overwritten
          </Pill>
        </div>
      </div>

      <div style={{ position: "absolute", top: 218, left: 120, right: 120, bottom: SAFE.cardFloor + 30 }}>
        <TerminalCard title="walrus-memory.log" badge={
          <div style={{ fontFamily: mono, fontSize: 13, color: COLORS.dimmer }}>append-only</div>
        }>
          <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
            {rows.map((r) => {
              const op = interpolate(frame, [r.at, r.at + 10], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
              return (
                <div
                  key={r.id}
                  style={{
                    display: "flex",
                    alignItems: "baseline",
                    gap: 16,
                    opacity: op,
                    transform: `translateX(${interpolate(frame, [r.at, r.at + 10], [-10, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })}px)`,
                    padding: "7px 0",
                    borderBottom: `1px solid ${COLORS.border}`,
                  }}
                >
                  <span style={{ fontFamily: mono, fontSize: 17, color: r.color, width: 92, fontWeight: 500 }}>{r.id}</span>
                  <span style={{ fontFamily: mono, fontSize: 19, color: COLORS.text, flex: 1 }}>{r.text}</span>
                  <span style={{ fontFamily: mono, fontSize: 14, color: r.color, opacity: 0.8 }}>{r.tag}</span>
                </div>
              );
            })}
          </div>

          <div style={{ marginTop: 22, opacity: citationOpacity }}>
            <div style={{ fontFamily: mono, fontSize: 15, color: COLORS.dim, marginBottom: 10 }}>
              memory_recall_cited
            </div>
            <Pill delay={citationAt} color={COLORS.emerald} bg={COLORS.emeraldDim} style={{ fontSize: 17, padding: "8px 16px" }}>
              rule#04 &lt;- fix#03 &lt;- fix#02 &lt;- obs#01
            </Pill>
          </div>
        </TerminalCard>
      </div>
    </AbsoluteFill>
  );
};
