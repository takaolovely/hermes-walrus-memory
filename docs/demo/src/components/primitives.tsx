import React from "react";
import { interpolate, useCurrentFrame, spring, useVideoConfig } from "remotion";
import { COLORS, mono } from "../theme";

/**
 * TerminalCard: a native flexbox card that looks like a terminal window.
 * No screenshots, no image layers. Every pixel is rendered from props.
 */
export const TerminalCard: React.FC<{
  title?: string;
  badge?: React.ReactNode;
  style?: React.CSSProperties;
  children: React.ReactNode;
  accent?: string;
  delay?: number;
}> = ({ title, badge, style, children, accent = COLORS.emerald, delay = 0 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = spring({ frame: frame - delay, fps, config: { damping: 200, mass: 0.6 } });
  const y = interpolate(enter, [0, 1], [18, 0]);
  const opacity = interpolate(enter, [0, 1], [0, 1]);

  return (
    <div
      style={{
        background: COLORS.card,
        border: `1px solid ${COLORS.border}`,
        borderRadius: 14,
        overflow: "hidden",
        boxShadow: "0 24px 60px rgba(0,0,0,0.55)",
        opacity,
        transform: `translateY(${y}px)`,
        ...style,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          padding: "12px 18px",
          borderBottom: `1px solid ${COLORS.border}`,
          background: COLORS.cardAlt,
        }}
      >
        <div style={{ display: "flex", gap: 7 }}>
          {["#ff5f57", "#febc2e", "#28c840"].map((c) => (
            <div key={c} style={{ width: 11, height: 11, borderRadius: 999, background: c, opacity: 0.85 }} />
          ))}
        </div>
        {title && (
          <div style={{ fontFamily: mono, fontSize: 15, color: COLORS.dim, letterSpacing: 0.2 }}>
            {title}
          </div>
        )}
        <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>{badge}</div>
      </div>
      <div style={{ padding: "20px 24px", fontFamily: mono }}>{children}</div>
    </div>
  );
};

/** A single terminal line that fades and slides in at `at` frames. */
export const Line: React.FC<{
  at: number;
  children: React.ReactNode;
  color?: string;
  size?: number;
  style?: React.CSSProperties;
  indent?: number;
}> = ({ at, children, color = COLORS.text, size = 19, style, indent = 0 }) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [at, at + 8], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const x = interpolate(frame, [at, at + 8], [-8, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <div
      style={{
        fontFamily: mono,
        fontSize: size,
        lineHeight: 1.62,
        color,
        opacity,
        transform: `translateX(${x}px)`,
        paddingLeft: indent,
        whiteSpace: "pre",
        ...style,
      }}
    >
      {children}
    </div>
  );
};

/** Green pill used for the citation chain and status badges. */
export const Pill: React.FC<{
  children: React.ReactNode;
  color?: string;
  bg?: string;
  delay?: number;
  style?: React.CSSProperties;
}> = ({ children, color = COLORS.emerald, bg = COLORS.emeraldDim, delay = 0, style }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame: frame - delay, fps, config: { damping: 14, mass: 0.4 } });
  const scale = interpolate(s, [0, 1], [0.9, 1]);
  const opacity = interpolate(s, [0, 1], [0, 1]);
  return (
    <div
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 7,
        padding: "5px 13px",
        borderRadius: 7,
        background: bg,
        border: `1px solid ${color}44`,
        color,
        fontFamily: mono,
        fontSize: 14,
        fontWeight: 500,
        opacity,
        transform: `scale(${scale})`,
        ...style,
      }}
    >
      {children}
    </div>
  );
};

/** Small key/value status row used in verify outputs. */
export const KV: React.FC<{
  k: string;
  v: React.ReactNode;
  at: number;
  valueColor?: string;
}> = ({ k, v, at, valueColor = COLORS.emerald }) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [at, at + 7], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <div style={{ display: "flex", gap: 10, opacity, fontFamily: mono, fontSize: 19, lineHeight: 1.66, whiteSpace: "pre" }}>
      <span style={{ color: COLORS.dim, minWidth: 250 }}>{k}</span>
      <span style={{ color: valueColor, fontWeight: 500 }}>{v}</span>
    </div>
  );
};
