import React from "react";
import { AbsoluteFill, useCurrentFrame, interpolate } from "remotion";
import { COLORS, mono, SAFE } from "../theme";
import { TerminalCard, Pill } from "./primitives";

/** Scene 6: one-line install, tool list, test result, repo URL. */
export const Scene6: React.FC<{ duration: number }> = ({ duration }) => {
  const frame = useCurrentFrame();

  const tools = [
    "memory_observe", "memory_correct", "memory_recall_cited",
    "memory_provenance_diff", "memory_import", "walrus_sync", "walrus_verify",
  ];

  const cmdAt = 20;
  const cmd = "hermes plugins install https://github.com/takaolovely/hermes-walrus-memory";
  const typed = cmd.slice(0, Math.round(interpolate(frame, [cmdAt, cmdAt + 54], [0, cmd.length], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })));

  const statsAt = 130;

  return (
    <AbsoluteFill style={{ background: COLORS.bg, padding: "0 120px" }}>
      <div style={{ position: "absolute", top: 104, left: 120, right: 120 }}>
        <div style={{ fontFamily: mono, fontSize: 15, color: COLORS.dimmer, letterSpacing: 3, marginBottom: 16 }}>
          INSTALL
        </div>
        <div style={{ fontFamily: mono, fontSize: 44, color: COLORS.text, fontWeight: 500, lineHeight: 1.2 }}>
          One line. No keys required.
        </div>
      </div>

      <div style={{ position: "absolute", top: 268, left: 120, right: 120 }}>
        <TerminalCard title="terminal">
          <div style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 20, lineHeight: 1.6 }}>
            <span style={{ color: COLORS.emerald }}>$</span>
            <span style={{ color: COLORS.text, whiteSpace: "pre-wrap" }}>{typed}</span>
            <span style={{ color: COLORS.emerald, opacity: Math.floor(frame / 14) % 2 === 0 ? 1 : 0 }}>|</span>
          </div>
        </TerminalCard>
      </div>

      <div style={{ position: "absolute", top: 430, left: 120, right: 120, display: "flex", gap: 26, bottom: SAFE.cardFloor + 16 }}>
        <div style={{ flex: 1.35 }}>
          <TerminalCard title="7 tools" style={{ height: "100%" }}>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 9 }}>
              {tools.map((t, i) => (
                <Pill key={t} delay={statsAt + i * 5} color={COLORS.cyan} bg={COLORS.cyanDim} style={{ fontSize: 14 }}>
                  {t}
                </Pill>
              ))}
            </div>
          </TerminalCard>
        </div>

        <div style={{ flex: 1 }}>
          <TerminalCard title="result" style={{ height: "100%" }}>
            <div style={{ opacity: interpolate(frame, [statsAt + 30, statsAt + 46], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }) }}>
              <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 8 }}>
                <span style={{ fontSize: 34, color: COLORS.emerald, fontWeight: 700 }}>93</span>
                <span style={{ fontSize: 17, color: COLORS.dim }}>tests passing</span>
              </div>
              <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 8 }}>
                <span style={{ fontSize: 34, color: COLORS.emerald, fontWeight: 700 }}>0</span>
                <span style={{ fontSize: 17, color: COLORS.dim }}>Python deps in Mode 1</span>
              </div>
              <div style={{ fontFamily: mono, fontSize: 15, color: COLORS.dimmer, marginTop: 12 }}>
                github.com/takaolovely/hermes-walrus-memory
              </div>
            </div>
          </TerminalCard>
        </div>
      </div>
    </AbsoluteFill>
  );
};
