/**
 * Product art for the public site, drawn from simple geometry in the same
 * style as the bead-moon logo (decision 0011). No photos: everything here is
 * original and ships inside the bundle.
 */
import { useId } from "react";
import { Bead } from "@/portal/Logo";
import type { BeadShape, CharmKind, Finish, FindingKind } from "./content";

const METAL: Record<Finish, [string, string, string]> = {
  gold: ["#f6dc8c", "#cf9d34", "#8a6418"],
  rhodium: ["#f7f8fb", "#c3cad5", "#7d8695"],
  bronze: ["#cfa274", "#8f643b", "#573a1f"],
};

const THREAD = "#a8957f";

function MetalGradient({ id, finish }: { id: string; finish: Finish }) {
  const [light, mid, dark] = METAL[finish];
  return (
    <linearGradient id={id} x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stopColor={light} />
      <stop offset="0.5" stopColor={mid} />
      <stop offset="1" stopColor={dark} />
    </linearGradient>
  );
}

function star(x: number, y: number, size: number): string {
  return (
    Array.from({ length: 10 }, (_, k) => {
      const r = k % 2 ? size * 0.45 : size;
      const a = -Math.PI / 2 + (k * Math.PI) / 5;
      return `${k ? "L" : "M"}${(x + r * Math.cos(a)).toFixed(2)} ${(y + r * Math.sin(a)).toFixed(2)}`;
    }).join("") + "Z"
  );
}

/* ------------------------------------------------------------------ beads */

/** One glass bead on a short length of thread. */
export function BeadArt({ shape, colors, className }: { shape: BeadShape; colors: [string, string]; className?: string }) {
  const [body, accent] = colors;
  return (
    <svg viewBox="0 0 100 100" className={className} aria-hidden="true">
      <line x1={4} y1={50} x2={96} y2={50} stroke={THREAD} strokeWidth={1.4} />
      {shape === "round" && (
        <>
          <Bead x={50} y={50} r={26} fill={body} />
          {[
            [40, 46],
            [58, 42],
            [52, 62],
          ].map(([x, y]) => (
            <circle key={`${x}-${y}`} cx={x} cy={y} r={4.2} fill={accent} opacity={0.9} />
          ))}
        </>
      )}
      {shape === "faceted" && <Faceted body={body} accent={accent} />}
      {shape === "swirl" && (
        <>
          <Bead x={50} y={50} r={28} fill={body} />
          <path
            d="M50 50 m-2 0 a4 4 0 1 1 6 3 a9 9 0 1 1 -13 -9 a14 14 0 1 1 -2 22 a19 19 0 0 1 -6 -20"
            fill="none"
            stroke={accent}
            strokeWidth={3.4}
            strokeLinecap="round"
            opacity={0.9}
          />
          <ellipse cx={40} cy={36} rx={8} ry={5} fill="#fff" opacity={0.55} />
        </>
      )}
      {shape === "lentil" && (
        <>
          <ellipse cx={50} cy={50} rx={32} ry={18} fill={body} />
          <ellipse cx={50} cy={53} rx={28} ry={13} fill="#000" opacity={0.12} />
          <ellipse cx={50} cy={50} rx={27} ry={13} fill={body} />
          <ellipse cx={50} cy={50} rx={20} ry={8} fill="none" stroke={accent} strokeWidth={2.4} />
          <ellipse cx={38} cy={43} rx={9} ry={3.4} fill="#fff" opacity={0.5} />
        </>
      )}
    </svg>
  );
}

function Faceted({ body, accent }: { body: string; accent: string }) {
  const pts = Array.from({ length: 8 }, (_, k) => {
    const a = (Math.PI / 4) * k + Math.PI / 8;
    return [50 + 28 * Math.cos(a), 50 + 28 * Math.sin(a)];
  });
  const inner = pts.map(([x, y]) => [50 + (x - 50) * 0.45, 50 + (y - 50) * 0.45]);
  return (
    <g>
      <polygon points={pts.map((p) => p.join(",")).join(" ")} fill={body} />
      {pts.map(([x, y], k) => {
        const [nx, ny] = pts[(k + 1) % 8];
        const [ix, iy] = inner[k];
        const [jx, jy] = inner[(k + 1) % 8];
        return (
          <polygon
            key={k}
            points={`${x},${y} ${nx},${ny} ${jx},${jy} ${ix},${iy}`}
            fill={k >= 1 && k <= 3 ? accent : "#fff"}
            opacity={k >= 1 && k <= 3 ? 0.45 : k >= 5 ? 0.3 : 0.08}
          />
        );
      })}
      <polygon points={inner.map((p) => p.join(",")).join(" ")} fill="#fff" opacity={0.18} />
    </g>
  );
}

/* ----------------------------------------------------------------- charms */

/** One charm on its jump ring. */
export function CharmArt({ kind, finish, className }: { kind: CharmKind; finish: Finish; className?: string }) {
  const id = useId().replace(/:/g, "");
  const fill = `url(#m${id})`;
  const dark = METAL[finish][2];
  return (
    <svg viewBox="0 0 100 100" className={className} aria-hidden="true">
      <defs>
        <MetalGradient id={`m${id}`} finish={finish} />
      </defs>
      <circle cx={50} cy={13} r={6} fill="none" stroke={fill} strokeWidth={2.6} />
      <circle cx={50} cy={24} r={4.5} fill="none" stroke={fill} strokeWidth={2.6} />
      <CharmShape kind={kind} fill={fill} dark={dark} />
    </svg>
  );
}

function CharmShape({ kind, fill, dark }: { kind: CharmKind; fill: string; dark: string }) {
  switch (kind) {
    case "moon":
      return (
        <g>
          <path d="M52 30 A28 28 0 0 0 52 86 A34 34 0 0 1 52 30Z" fill={fill} />
          <path d={star(62, 58, 9)} fill={fill} stroke={dark} strokeWidth={0.6} strokeOpacity={0.4} />
        </g>
      );
    case "bee":
      return (
        <g>
          <ellipse cx={37} cy={46} rx={11} ry={7} transform="rotate(-25 37 46)" fill={fill} opacity={0.75} />
          <ellipse cx={63} cy={46} rx={11} ry={7} transform="rotate(25 63 46)" fill={fill} opacity={0.75} />
          <circle cx={50} cy={37} r={7} fill={fill} />
          <ellipse cx={50} cy={62} rx={13} ry={18} fill={fill} />
          {[56, 64, 72].map((y) => (
            <path key={y} d={`M38 ${y} Q50 ${y + 3} 62 ${y}`} fill="none" stroke={dark} strokeWidth={2.4} opacity={0.65} />
          ))}
        </g>
      );
    case "lotus":
      return (
        <g>
          {[-62, -32, 0, 32, 62].map((deg) => (
            <path
              key={deg}
              d="M50 82 C39 66 41 46 50 34 C59 46 61 66 50 82Z"
              transform={`rotate(${deg} 50 82)`}
              fill={fill}
              stroke={dark}
              strokeWidth={0.8}
              strokeOpacity={0.35}
            />
          ))}
          <path d="M30 84 Q50 92 70 84" fill="none" stroke={fill} strokeWidth={3} strokeLinecap="round" />
        </g>
      );
    case "cactus":
      return (
        <g fill={fill}>
          <rect x={43} y={30} width={14} height={54} rx={7} />
          <rect x={27} y={48} width={10} height={22} rx={5} />
          <rect x={31} y={63} width={14} height={7} rx={3.5} />
          <rect x={63} y={40} width={10} height={22} rx={5} />
          <rect x={55} y={55} width={14} height={7} rx={3.5} />
          <line x1={50} y1={36} x2={50} y2={80} stroke={dark} strokeWidth={1.2} opacity={0.35} />
        </g>
      );
    case "initial":
      return (
        <g>
          <circle cx={50} cy={58} r={26} fill={fill} />
          <circle cx={50} cy={58} r={21} fill="none" stroke={dark} strokeWidth={1} opacity={0.35} />
          <text
            x={50}
            y={70}
            textAnchor="middle"
            fontSize={34}
            fontStyle="italic"
            fontWeight={600}
            fill={dark}
            opacity={0.75}
            style={{ fontFamily: "var(--font-display)" }}
          >
            A
          </text>
        </g>
      );
    case "acorn":
      return (
        <g>
          <path d="M33 54 Q33 80 50 88 Q67 80 67 54Z" fill={fill} />
          <path d="M27 56 Q28 32 50 30 Q72 32 73 56Z" fill={fill} stroke={dark} strokeWidth={1} strokeOpacity={0.45} />
          {[36, 44, 52, 60, 68].map((x) => (
            <line key={x} x1={x} y1={38} x2={x - 4} y2={54} stroke={dark} strokeWidth={1} opacity={0.35} />
          ))}
        </g>
      );
    case "mushroom":
      return (
        <g>
          <rect x={42} y={56} width={16} height={28} rx={6} fill={fill} />
          <path d="M22 60 Q24 28 50 28 Q76 28 78 60Z" fill={fill} stroke={dark} strokeWidth={1} strokeOpacity={0.45} />
          {[
            [38, 44, 4],
            [56, 38, 3.4],
            [64, 50, 3],
          ].map(([x, y, r]) => (
            <circle key={`${x}-${y}`} cx={x} cy={y} r={r} fill={dark} opacity={0.3} />
          ))}
        </g>
      );
    case "shell":
      return (
        <g>
          <path d="M50 86 L24 52 Q50 22 76 52Z" fill={fill} />
          {[30, 40, 50, 60, 70].map((x) => (
            <line key={x} x1={50} y1={84} x2={x} y2={x === 50 ? 32 : 40 + Math.abs(50 - x) * 0.4} stroke={dark} strokeWidth={1.2} opacity={0.4} />
          ))}
        </g>
      );
    case "leaf":
      return (
        <g>
          <path d="M50 88 C26 70 30 42 50 30 C70 42 74 70 50 88Z" fill={fill} />
          <line x1={50} y1={34} x2={50} y2={86} stroke={dark} strokeWidth={1.4} opacity={0.4} />
          {[48, 60, 72].map((y) => (
            <g key={y} stroke={dark} strokeWidth={1} opacity={0.35}>
              <line x1={50} y1={y + 6} x2={38} y2={y} />
              <line x1={50} y1={y + 6} x2={62} y2={y} />
            </g>
          ))}
        </g>
      );
  }
}

/* --------------------------------------------------------------- findings */

export function FindingArt({ kind, className }: { kind: FindingKind; className?: string }) {
  const id = useId().replace(/:/g, "");
  const metal = `url(#f${id})`;
  return (
    <svg viewBox="0 0 100 100" className={className} aria-hidden="true">
      <defs>
        <MetalGradient id={`f${id}`} finish={kind === "clasp" ? "gold" : "rhodium"} />
      </defs>
      {kind === "rings" &&
        [
          [32, 56, 10],
          [56, 44, 14],
          [70, 66, 7],
        ].map(([x, y, r]) => <circle key={`${x}-${y}`} cx={x} cy={y} r={r} fill="none" stroke={metal} strokeWidth={3.4} />)}
      {kind === "clasp" && (
        <g fill="none" stroke={metal} strokeLinecap="round">
          <circle cx={50} cy={18} r={6} strokeWidth={3} />
          <path d="M44 28 Q30 46 36 66 Q42 84 54 80 Q66 74 62 54 Q58 36 50 28" strokeWidth={6} />
          <path d="M60 44 L66 60" strokeWidth={3} />
        </g>
      )}
      {kind === "wire" && (
        <g>
          <circle cx={50} cy={50} r={32} fill="#e9dfd0" />
          {[28, 24, 20, 16].map((r) => (
            <circle key={r} cx={50} cy={50} r={r} fill="none" stroke={metal} strokeWidth={3} />
          ))}
          <circle cx={50} cy={50} r={8} fill="#fbf6ee" stroke="#cdbda5" strokeWidth={1.5} />
          <path d="M78 46 Q90 40 94 28" fill="none" stroke={metal} strokeWidth={2} />
        </g>
      )}
      {kind === "memory" && (
        <g fill="none" stroke={metal} strokeWidth={2.6}>
          {[0, 1, 2, 3].map((k) => (
            <ellipse key={k} cx={50} cy={40 + k * 7} rx={30} ry={13} />
          ))}
          <circle cx={20} cy={61} r={3} fill="#7d8695" stroke="none" />
          <circle cx={80} cy={40} r={3} fill="#7d8695" stroke="none" />
        </g>
      )}
    </svg>
  );
}

/* ------------------------------------------------------------- big pieces */

/** The hero necklace: graduated glass beads in Amber Hollow colors, a moon charm at the low point. */
export function HeroStrand({ className }: { className?: string }) {
  const colors = ["#e39a2d", "#a8481f", "#2d5443", "#c87f3a", "#eadfe8", "#2f45b5", "#5fae9c"];
  const count = 19;
  const beads = Array.from({ length: count }, (_, i) => {
    const t = i / (count - 1);
    const x = 40 + t * 520;
    const y = 40 + 250 * (1 - (2 * t - 1) ** 2);
    const r = 10 + 13 * Math.sin(Math.PI * t) + (i % 4 === 0 ? 3 : 0);
    return { x, y, r, fill: colors[i % colors.length], i };
  });
  const low = beads[Math.floor(count / 2)];
  return (
    <svg viewBox="0 0 600 440" className={className} aria-hidden="true">
      <path d={`M${beads[0].x} ${beads[0].y} Q 300 540 ${beads[count - 1].x} ${beads[count - 1].y}`} fill="none" stroke={THREAD} strokeWidth={2} />
      <line x1={low.x} y1={low.y + low.r} x2={low.x} y2={low.y + low.r + 34} stroke={THREAD} strokeWidth={1.6} />
      <g className="hl-rise" style={{ animationDelay: "500ms" }}>
        <svg x={low.x - 55} y={low.y + low.r + 14} width={110} height={110} viewBox="0 0 100 100" overflow="visible">
          <CharmArtInner kind="moon" finish="gold" />
        </svg>
      </g>
      {beads.map((b) => (
        <g key={b.i} className="hl-rise" style={{ animationDelay: `${b.i * 35}ms` }}>
          <Bead x={b.x} y={b.y} r={b.r} fill={b.fill} />
        </g>
      ))}
    </svg>
  );
}

/** A short strand for a collection banner, with its charms hanging below. */
export function CollectionStrand({
  palette,
  charms,
  finish,
  thread = THREAD,
  className,
}: {
  palette: string[];
  charms: CharmKind[];
  finish: Finish;
  thread?: string;
  className?: string;
}) {
  const count = 13;
  const beads = Array.from({ length: count }, (_, i) => {
    const t = i / (count - 1);
    return { x: 20 + t * 280, y: 30 + 46 * (1 - (2 * t - 1) ** 2), r: 7 + 5 * Math.sin(Math.PI * t), fill: palette[i % palette.length], i };
  });
  const hangs = charms.map((kind, k) => ({ kind, bead: beads[Math.round(((k + 1) * (count - 1)) / (charms.length + 1))] }));
  return (
    <svg viewBox="0 0 320 190" className={className} aria-hidden="true">
      <path d={`M20 30 Q160 122 300 30`} fill="none" stroke={thread} strokeWidth={1.4} />
      {hangs.map(({ kind, bead }) => (
        <g key={kind}>
          <line x1={bead.x} y1={bead.y} x2={bead.x} y2={bead.y + 28} stroke={thread} strokeWidth={1.2} />
          <svg x={bead.x - 32} y={bead.y + 14} width={64} height={64} viewBox="0 0 100 100" overflow="visible">
            <CharmArtInner kind={kind} finish={finish} />
          </svg>
        </g>
      ))}
      {beads.map((b) => (
        <Bead key={b.i} x={b.x} y={b.y} r={b.r} fill={b.fill} />
      ))}
    </svg>
  );
}

/** CharmArt without its own <svg>, for nesting inside a bigger drawing. */
function CharmArtInner({ kind, finish }: { kind: CharmKind; finish: Finish }) {
  const id = useId().replace(/:/g, "");
  const fill = `url(#c${id})`;
  return (
    <g>
      <defs>
        <MetalGradient id={`c${id}`} finish={finish} />
      </defs>
      <circle cx={50} cy={24} r={4.5} fill="none" stroke={fill} strokeWidth={2.6} />
      <CharmShape kind={kind} fill={fill} dark={METAL[finish][2]} />
    </g>
  );
}
