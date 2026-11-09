import React from "react";
import { Composition } from "remotion";
import { Demo, TOTAL_FRAMES } from "./Demo";

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="Demo"
      component={Demo}
      durationInFrames={TOTAL_FRAMES}
      fps={60}
      width={1920}
      height={1080}
    />
  );
};

