import React from 'react';
import {
  AbsoluteFill,
  Audio,
  Composition,
  Img,
  Sequence,
  Video,
  getInputProps,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';

type Visual = { type: 'video' | 'image' | 'none'; src: string };
type Scene = {
  index: number;
  duration: number;
  visual: Visual;
  narration: string | null;
  lead: number;
  sfx: string | null;
  caption: string | null;
};
type Input = {
  fps: number;
  width: number;
  height: number;
  documentary: boolean;
  captions: boolean;
  music: string | null;
  scenes: Scene[];
};

const EMPTY: Input = {
  fps: 30,
  width: 1920,
  height: 1080,
  documentary: false,
  captions: true,
  music: null,
  scenes: [],
};

// All media paths are written relative to the data/ directory, which is
// symlinked as remotion/public -> ../data, so staticFile() resolves them.
function srcFor(p: string): string {
  return staticFile(p);
}

const NOISE_SVG =
  "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='240' height='240'%3E" +
  "%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E" +
  "%3Crect width='240' height='240' filter='url(%23n)'/%3E%3C/svg%3E";

// Fade in/out that stays valid (strictly increasing range) for any duration.
function safeFade(frame: number, dur: number, fps: number, inS: number, outS: number): number {
  const maxFade = Math.max(Math.floor((dur - 1) / 2), 0);
  const fIn = Math.min(Math.round(fps * inS), maxFade);
  const fOut = Math.min(Math.round(fps * outS), maxFade);
  if (fIn + fOut >= dur) return 1;
  const end = dur - fOut;
  if (fIn >= end) return 1;
  return interpolate(frame, [0, fIn, end, dur], [0, 1, 1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
}

const FilmGrain: React.FC = () => {
  const frame = useCurrentFrame();
  const x = (frame * 13) % 240;
  const y = (frame * 7) % 240;
  return (
    <AbsoluteFill
      style={{
        backgroundImage: `url("${NOISE_SVG}")`,
        backgroundSize: '240px 240px',
        backgroundPosition: `${x}px ${y}px`,
        opacity: 0.12,
        mixBlendMode: 'overlay',
        pointerEvents: 'none',
      }}
    />
  );
};

const SceneContent: React.FC<{ scene: Scene; documentary: boolean; captions: boolean }> = ({
  scene,
  documentary,
  captions,
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  const progress = frame / Math.max(durationInFrames, 1);
  const kenBurns = 1 + 0.06 * progress;
  const v = scene.visual;

  // Dip-to-black at scene boundaries (classic archival transition).
  const opacity = safeFade(frame, durationInFrames, fps, 0.5, 0.5);
  const captionOpacity = safeFade(frame, durationInFrames, fps, 0.5, 0.6);

  return (
    <AbsoluteFill style={{ backgroundColor: '#000', overflow: 'hidden', opacity }}>
      <AbsoluteFill
        style={{
          filter: documentary ? 'sepia(0.55) saturate(0.78) contrast(1.05)' : undefined,
        }}
      >
        {v.type === 'video' ? (
          <Video
            src={srcFor(v.src)}
            style={{ width: '100%', height: '100%', objectFit: 'cover' }}
          />
        ) : v.type === 'image' ? (
          <Img
            src={srcFor(v.src)}
            style={{
              width: '100%',
              height: '100%',
              objectFit: 'cover',
              transform: `scale(${kenBurns})`,
            }}
          />
        ) : null}
      </AbsoluteFill>

      {documentary && (
        <>
          <AbsoluteFill
            style={{
              background:
                'radial-gradient(ellipse at center, transparent 55%, rgba(0,0,0,0.55) 100%)',
            }}
          />
          <FilmGrain />
          <AbsoluteFill style={{ justifyContent: 'space-between' }}>
            <div style={{ height: '11%', background: '#000' }} />
            <div style={{ height: '11%', background: '#000' }} />
          </AbsoluteFill>
        </>
      )}

      {captions && scene.caption ? (
        <AbsoluteFill style={{ justifyContent: 'flex-end', alignItems: 'center', paddingBottom: 160 }}>
          <div
            style={{
              background: 'rgba(0,0,0,0.45)',
              padding: '10px 24px',
              borderRadius: 4,
              color: '#ffffff',
              fontSize: 42,
              fontWeight: 500,
              maxWidth: '82%',
              textAlign: 'center',
              opacity: captionOpacity,
            }}
          >
            {scene.caption}
          </div>
        </AbsoluteFill>
      ) : null}
    </AbsoluteFill>
  );
};

const VideoPipeline: React.FC<Input> = (props) => {
  const { fps } = useVideoConfig();
  const input: Input = props || EMPTY;

  let cursor = 0;
  const ranges = input.scenes.map((scene) => {
    const durationInFrames = Math.max(Math.round(scene.duration * fps), 1);
    const range = { scene, from: cursor, durationInFrames };
    cursor += durationInFrames;
    return range;
  });
  const total = Math.max(cursor, 1);

  return (
    <AbsoluteFill style={{ backgroundColor: '#000' }}>
      {ranges.map((r) => (
        <Sequence
          key={`v${r.scene.index}`}
          from={r.from}
          durationInFrames={r.durationInFrames}
        >
          <SceneContent
            scene={r.scene}
            documentary={input.documentary}
            captions={input.captions}
          />
        </Sequence>
      ))}

      {ranges.map((r) => (
        <React.Fragment key={`a${r.scene.index}`}>
          {r.scene.narration ? (
            <Sequence
              from={r.from + Math.round(r.scene.lead * fps)}
              durationInFrames={r.durationInFrames}
            >
              <Audio src={srcFor(r.scene.narration)} />
            </Sequence>
          ) : null}
          {r.scene.sfx ? (
            <Sequence from={r.from} durationInFrames={r.durationInFrames}>
              <Audio src={srcFor(r.scene.sfx)} />
            </Sequence>
          ) : null}
        </React.Fragment>
      ))}

      {input.music ? (
        <Sequence from={0} durationInFrames={total}>
          <Audio src={srcFor(input.music)} volume={0.18} loop />
        </Sequence>
      ) : null}
    </AbsoluteFill>
  );
};

export const RemotionRoot: React.FC = () => {
  const props = (getInputProps() as Input | null) ?? EMPTY;
  const fps = props.fps || 30;
  const totalFrames = Math.max(
    props.scenes.reduce((acc, s) => acc + Math.max(Math.round(s.duration * fps), 1), 0),
    1,
  );

  return (
    <Composition
      id="VideoPipeline"
      component={VideoPipeline}
      durationInFrames={totalFrames}
      fps={fps}
      width={props.width || 1920}
      height={props.height || 1080}
    />
  );
};
