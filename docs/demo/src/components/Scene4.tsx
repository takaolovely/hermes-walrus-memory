import React from "react";
import { AbsoluteFill, useCurrentFrame, interpolate } from "remotion";
import { COLORS, mono, SAFE } from "../theme";
import { TerminalCard, Line, KV, Pill } from "./primitives";

/**
 * Scene 4: tamper evidence. A character is edited on disk, fix#02 flips to red,
 * and verify names the exact line that broke.
 */
export const Scene4: React.FC<{ duration: number }> = ({ duration }) => {
  const frame = useCurrentFrame();

  const editAt = 78;
  const flipAt = 96;
  const rows = [
    { id: "obs#01", text: "The user ships on Vercel.", color: COLORS.cyan },
    { id: "fix#02", text: "The user ships on Railway, Vercel for static.", color: COLORS.amber },
    { id: "fix#03", text: "The user ships on Fly.io first, Vercel for static.", color: COLORS.amber },
    { id: "rule#04", text: "Fly.io first, Vercel for static.", color: COLORS.emerald },
  ];

  const tamper = interpolate(frame, [flipAt, flipAt + 10], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const verifyAt = 156;

  return (
    <AbsoluteFill style={{ background: COLORS.bg, padding: "0 120px" }}>
      <div style={{ position: "absolute", top: 66, left: 120, right: 120 }}>
        <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between" }}>
          <div>
            <div style={{ fontFamily: mono, fontSize: 15, color: COLORS.dimmer, letterSpacing: 3, marginBottom: 12 }}>
              TAMPER EVIDENCE
            </div>
            <div style={{ fontFamily: mono, fontSize: 40, color: COLORS.text, fontWeight: 500 }}>
              Each line hashes the one before.
            </div>
          </div>
          <Pill color={COLORS.red} bg={COLORS.redDim} delay={flipAt}>
            SHA-256 chained
          </Pill>
        </div>
      </div>

      <div style={{ position: "absolute", top: 190, left: 120, right: 120, bottom: SAFE.cardFloor + 26 }}>
        <TerminalCard title="walrus-memory.log" badge={
          <div style={{ fontFamily: mono, fontSize: 13, color: interpolate(frame, [flipAt, flipAt + 8], [0.4, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }) > 0.5 ? COLORS.red : COLORS.dimmer }}>
            edited on disk
          </div>
        }>
          <div style={{ display: "flex", flexDirection: "column" }}>
            {rows.map((r, i) => {
              const isBad = r.id === "fix#02";
              const bad = isBad ? tamper : 0;
              return (
                <div
                  key={r.id}
                  style={{
                    display: "flex",
                    alignItems: "baseline",
                    gap: 14,
                    padding: "6px 10px",
                    marginLeft: -10,
                    borderRadius: 6,
                    background: `rgba(239,68,68,${0.13 * bad})`,
                    outline: bad > 0.1 ? `1px solid rgba(239,68,68,${0.5 * bad})` : "none",
                    fontFamily: mono,
                    fontSize: 18,
                    lineHeight: 1.6,
                  }}
                >
                  <span style={{ color: isBad && bad > 0.3 ? COLORS.red : r.color, width: 88 }}>{r.id}</span>
                  <span style={{ color: isBad && bad > 0.3 ? "#fca5a5" : COLORS.text }}>
                    {isBad && bad > 0.3
                      ? <span>The user ships on <span style={{ color: COLORS.red, textDecoration: "underline" }}>Railway</span>, Vercel for static.</span>
                      : r.text}
                  </span>
                  {isBad && bad > 0.3 && (
                    <span style={{ marginLeft: "auto", color: COLORS.red, fontSize: 14, opacity: bad }}>hash mismatch</span>
                  )}
                </div>
              );
            })}
          </div>

          <div style={{ marginTop: 14, paddingTop: 14, borderTop: `1px solid ${COLORS.border}` }}>
            <Line at={30} color={COLORS.dim} size={16}>
              $ sed -i 's/Fly.io/Railway/' ~/.hermes/walrus-memory.log
            </Line>
          </div>

          <div style={{ marginTop: 14, opacity: interpolate(frame, [verifyAt, verifyAt + 12], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }) }}>
            <div style={{ fontFamily: mono, fontSize: 16, color: COLORS.dim, marginBottom: 8 }}>walrus_verify</div>
            <KV k="chain_ok" v="false" at={verifyAt + 8} valueColor={COLORS.red} />
            <KV k="broken_at" v="2" at={verifyAt + 20} valueColor={COLORS.amber} />
            <KV k="hash mismatch at" v="fix#02" at={verifyAt + 32} valueColor={COLORS.red} />
          </div>
        </TerminalCard>
      </div>
    </AbsoluteFill>
  );
};
