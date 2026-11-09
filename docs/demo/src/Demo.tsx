import React from "react";
import { AbsoluteFill, Sequence, Audio, staticFile, useCurrentFrame, interpolate } from "remotion";
import manifest from "../audio/manifest.json";
import subsData from "../audio/subs.json";
import { COLORS } from "./theme";
import { Scene1 } from "./components/Scene1";
import { Scene2 } from "./components/Scene2";
import { Scene3 } from "./components/Scene3";
import { Scene4 } from "./components/Scene4";
import { Scene5 } from "./components/Scene5";
import { Scene6 } from "./components/Scene6";
import { Subtitles, Cue } from "./components/Subtitles";

const SCENES = [
  { key: "scene1", Comp: Scene1 },
  { key: "scene2", Comp: Scene2 },
  { key: "scene3", Comp: Scene3 },
  { key: "scene4", Comp: Scene4 },
  { key: "scene5", Comp: Scene5 },
  { key: "scene6", Comp: Scene6 },
] as const;

const framesOf = (k: string) => (manifest as any)[k].frames as number;

/** All scene start frames, computed from the measured audio. */
const offsets: Record<string, number> = {};
let acc = 0;
for (const s of SCENES) {
  offsets[s.key] = acc;
  acc += framesOf(s.key);
}
export const TOTAL_FRAMES = acc;

/** Crossfade backdrop so scene changes read as cuts, not jumps. */
const Backdrop: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{ backgroundColor: COLORS.bg }}>
      <AbsoluteFill
        style={{
          background: "radial-gradient(1200px 700px at 50% 12%, rgba(16,185,129,0.055), rgba(7,8,9,0) 62%)",
        }}
      />
      <AbsoluteFill
        style={{
          background: "radial-gradient(900px 600px at 82% 92%, rgba(34,211,238,0.035), rgba(7,8,9,0) 60%)",
          opacity: 0.85,
        }}
      />
      {/* subtle vignette to keep focus center-frame */}
      <AbsoluteFill
        style={{
          boxShadow: "inset 0 0 260px 60px rgba(0,0,0,0.55)",
        }}
      />
      <AbsoluteFill
        style={{
          opacity: interpolate(frame % 60, [0, 30, 60], [0.4, 0.55, 0.4], { extrapolateRight: "clamp" }),
          background: "linear-gradient(180deg, rgba(255,255,255,0.012), rgba(0,0,0,0) 40%)",
        }}
      />
    </AbsoluteFill>
  );
};

export const Demo: React.FC = () => {
  return (
    <AbsoluteFill style={{ backgroundColor: COLORS.bg }}>
      <Backdrop />

      {SCENES.map(({ key, Comp }) => {
        const dur = framesOf(key);
        const cues = (subsData as any)[key] as Cue[];
        return (
          <Sequence key={key} from={offsets[key]} durationInFrames={dur} name={key}>
            <Comp duration={dur} />
            <Subtitles cues={cues} durationSeconds={dur / 60} />
            <Audio src={staticFile(`audio/${key}.mp3`)} />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
