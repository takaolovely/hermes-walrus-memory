import React from "react";
import { AbsoluteFill, useCurrentFrame, interpolate } from "remotion";
import { COLORS, mono, SAFE } from "../theme";
import { TerminalCard, Line, Pill } from "./primitives";

/** Scene 3: every answer carries the line it came from, and a timeline on ask-why. */
export const Scene3: React.FC<{ duration: number }> = ({ duration }) => {
  const frame = useCurrentFrame();

  const timeline = [
    { at: 132, label: "Observed", when: "2026-11-09 15:34", what: "The user ships on Vercel.", cite: "obs#01", color: COLORS.cyan },
    { at: 168, label: "Corrected", when: "2026-11-09 17:31", what: "Moved to Fly.io. Reason: user migrated.", cite: "fix#02", color: COLORS.amber },
    { at: 206, label: "Corrected", when: "2026-11-09 17:58", what: "Fly.io first. Reason: refined.", cite: "fix#03", color: COLORS.amber },
    { at: 244, label: "Rule", when: "2026-11-09 17:58", what: "Fly.io first, Vercel for static.", cite: "rule#04", color: COLORS.emerald },
  ];

  return (
    <AbsoluteFill style={{ background: COLORS.bg, padding: "0 120px" }}>
      <div style={{ position: "absolute", top: 74, left: 120, right: 120 }}>
        <div style={{ fontFamily: mono, fontSize: 15, color: COLORS.dimmer, letterSpacing: 3, marginBottom: 14 }}>
          PROVENANCE
        </div>
        <div style={{ fontFamily: mono, fontSize: 42, color: COLORS.text, fontWeight: 500 }}>
          Every answer cites its line.
        </div>
      </div>

      <div style={{ position: "absolute", top: 214, left: 120, right: 120, bottom: SAFE.cardFloor + 30 }}>
        <TerminalCard title="hermes">
          <Line at={6} color={COLORS.emerald} size={19}>
            <span style={{ color: COLORS.dimmer }}>{"["}user{" ] "}</span>Where do I deploy?
          </Line>
          <Line at={26} color={COLORS.dim} size={18}>
            {"  "}memory_recall_cited
          </Line>
          <Line at={36} size={20}>
            {"  -> "}<span style={{ color: COLORS.text }}>"Fly.io, Vercel for static"</span>
          </Line>
          <div style={{ marginTop: 6, marginBottom: 16 }}>
            <Pill delay={48} color={COLORS.emerald}>rule#04 &lt;- fix#03 &lt;- fix#02 &lt;- obs#01</Pill>
          </div>

          <Line at={82} color={COLORS.emerald} size={19}>
            <span style={{ color: COLORS.dimmer }}>{"["}user{" ] "}</span>Why did you think Vercel before?
          </Line>
          <Line at={100} color={COLORS.dim} size={18}>
            {"  "}memory_provenance_diff
          </Line>

          <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 2 }}>
            {timeline.map((t) => {
              const op = interpolate(frame, [t.at, t.at + 10], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
              return (
                <div key={t.cite} style={{ display: "flex", alignItems: "center", gap: 12, opacity: op, fontFamily: mono, fontSize: 17, lineHeight: 1.7 }}>
                  <span style={{ color: COLORS.dimmer, width: 128 }}>{t.when}</span>
                  <span style={{ color: t.color, width: 92 }}>{t.label}</span>
                  <span style={{ color: COLORS.text, flex: 1 }}>{t.what}</span>
                  <span style={{ color: t.color, opacity: 0.75 }}>{t.cite}</span>
                </div>
              );
            })}
          </div>
        </TerminalCard>
      </div>
    </AbsoluteFill>
  );
};
