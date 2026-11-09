import React from "react";
import { AbsoluteFill, useCurrentFrame, interpolate } from "remotion";
import { COLORS, mono, SAFE } from "../theme";
import { TerminalCard, KV, Pill, Line } from "./primitives";

/**
 * Scene 5: Walrus Mainnet sync, then the SEAL contrast. Same blobs, two outcomes
 * depending on whether a session key is present. Left card never resolves; right
 * card opens.
 */
export const Scene5: React.FC<{ duration: number }> = ({ duration }) => {
  const frame = useCurrentFrame();

  const syncAt = 18;
  const sealPanelAt = 210;
  const openAt = 330;

  const leftOpacity = interpolate(frame, [sealPanelAt, sealPanelAt + 14], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const rightOpacity = interpolate(frame, [sealPanelAt + 20, sealPanelAt + 34], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  return (
    <AbsoluteFill style={{ background: COLORS.bg, padding: "0 120px" }}>
      <div style={{ position: "absolute", top: 56, left: 120, right: 120 }}>
        <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between" }}>
          <div>
            <div style={{ fontFamily: mono, fontSize: 15, color: COLORS.dimmer, letterSpacing: 3, marginBottom: 10 }}>
              WALRUS MAINNET + MYSTEN SEAL
            </div>
            <div style={{ fontFamily: mono, fontSize: 38, color: COLORS.text, fontWeight: 500 }}>
              Same lines, on chain. Sealed by default.
            </div>
          </div>
          <Pill color={COLORS.violet} bg={COLORS.violetDim} delay={6}>
            Swee Mainnet
          </Pill>
        </div>
      </div>

      {/* Top: sync + verify */}
      <div style={{ position: "absolute", top: 172, left: 120, right: 120, height: 218 }}>
        <TerminalCard title="walrus_sync / walrus_verify">
          <div style={{ display: "flex", gap: 48 }}>
            <div style={{ flex: 1 }}>
              <Line at={syncAt} color={COLORS.dim} size={16}>$ export WALRUS_DELEGATE_KEY=... WALRUS_ACCOUNT_ID=0x21c2...</Line>
              <Line at={syncAt + 16} size={18} color={COLORS.text}>
                <span style={{ color: COLORS.emerald }}>memory_observe</span> {"->"} obs#07  <span style={{ color: COLORS.cyan }}>sync=synced</span>
              </Line>
              <Line at={syncAt + 30} size={16} color={COLORS.dimmer}>job 77fa9773-d3b6-4506</Line>
            </div>
            <div style={{ flex: 1 }}>
              <KV k="chain_ok" v="true" at={syncAt + 54} />
              <KV k="walrus_reachable" v="true" at={syncAt + 66} />
              <KV k="verified_on_walrus" v="true" at={syncAt + 78} />
              <KV k="walrus_lines" v="7" at={syncAt + 90} />
            </div>
          </div>
        </TerminalCard>
      </div>

      {/* Bottom: SEAL contrast */}
      <div style={{ position: "absolute", top: 418, left: 120, right: 120, bottom: SAFE.cardFloor + 16, display: "flex", gap: 26 }}>
        <div style={{ flex: 1, opacity: leftOpacity }}>
          <TerminalCard
            title="POST /api/recall"
            style={{ height: "100%", borderColor: "rgba(245,158,11,0.30)" }}
            badge={<Pill color={COLORS.amber} bg={COLORS.amberDim} delay={sealPanelAt + 8} style={{ fontSize: 12 }}>no x-seal-session</Pill>}
          >
            <KV k="encrypted_blobs_found" v="21" at={sealPanelAt + 16} valueColor={COLORS.amber} />
            <KV k="pulled" v="0" at={sealPanelAt + 28} valueColor={COLORS.dim} />
            <KV k="degraded" v="true" at={sealPanelAt + 40} valueColor={COLORS.amber} />
            <div style={{ marginTop: 14, fontFamily: mono, fontSize: 15, color: COLORS.dim, lineHeight: 1.55 }}>
              The relay can prove the memory exists.
              <br />
              It cannot read a word of it.
            </div>
          </TerminalCard>
        </div>

        <div style={{ flex: 1, opacity: rightOpacity }}>
          <TerminalCard
            title="POST /api/recall"
            style={{ height: "100%", borderColor: "rgba(16,185,129,0.34)" }}
            badge={<Pill color={COLORS.emerald} bg={COLORS.emeraldDim} delay={sealPanelAt + 26} style={{ fontSize: 12 }}>x-seal-session</Pill>}
          >
            <KV k="pulled" v="6" at={sealPanelAt + 34} />
            <KV k="dropped" v="0" at={sealPanelAt + 46} />
            <KV k="degraded" v="false" at={sealPanelAt + 58} />
            <div style={{ marginTop: 14, fontFamily: mono, fontSize: 15, color: COLORS.emerald, lineHeight: 1.55 }}>
              The session opens the blobs.
              <br />
              Nothing is dropped.
            </div>
          </TerminalCard>
        </div>
      </div>
    </AbsoluteFill>
  );
};
