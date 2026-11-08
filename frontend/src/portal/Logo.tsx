/**
 * The Hilda & Luna Beadworks mark: graduated glass beads on one thread form
 * a crescent moon, with an amber star charm hanging inside the curve.
 * Drawn from geometry (not path data) so the favicon and the logo match.
 */

export const BEAD = {
  cobalt: "#2f45b5",
  amber: "#e39a2d",
  opal: "#e7a3a6",
  sea: "#5fae9c",
  moonstone: "#c9d2e6",
} as const;

const ORDER = [BEAD.cobalt, BEAD.sea, BEAD.cobalt, BEAD.opal, BEAD.cobalt, BEAD.amber];
const CX = 50;
const CY = 50;
const R = 32;
const START = 50; // degrees; the crescent opens to the right
const END = 310;
const COUNT = 15;

const rad = (deg: number) => (deg * Math.PI) / 180;

/** Bead centres and sizes: largest in the middle of the strand, tapering to the tips. */
export const MOON_BEADS = Array.from({ length: COUNT }, (_, i) => {
  const t = i / (COUNT - 1);
  const a = rad(START + (END - START) * t);
  return {
    x: CX + R * Math.cos(a),
    y: CY + R * Math.sin(a),
    r: 2.4 + 6.2 * Math.sin(Math.PI * t),
    fill: ORDER[i % ORDER.length],
  };
});

function starPath(x: number, y: number, size: number): string {
  return (
    Array.from({ length: 10 }, (_, k) => {
      const r = k % 2 ? size * 0.45 : size;
      const a = -Math.PI / 2 + (k * Math.PI) / 5;
      return `${k ? "L" : "M"}${(x + r * Math.cos(a)).toFixed(2)} ${(y + r * Math.sin(a)).toFixed(2)}`;
    }).join("") + "Z"
  );
}

/** One glass bead: body, a soft lower shade and a highlight. */
export function Bead({ x, y, r, fill }: { x: number; y: number; r: number; fill: string }) {
  return (
    <g>
      <circle cx={x} cy={y} r={r} fill={fill} />
      <circle cx={x} cy={y + r * 0.18} r={r * 0.82} fill="#000" opacity={0.12} />
      <circle cx={x} cy={y} r={r * 0.86} fill={fill} />
      <ellipse cx={x - r * 0.32} cy={y - r * 0.36} rx={r * 0.3} ry={r * 0.2} fill="#fff" opacity={0.55} />
    </g>
  );
}

function MoonStrand({ thread }: { thread: string }) {
  const a0 = rad(START);
  const a1 = rad(END);
  const arc = `M${CX + R * Math.cos(a0)} ${CY + R * Math.sin(a0)} A${R} ${R} 0 1 1 ${CX + R * Math.cos(a1)} ${CY + R * Math.sin(a1)}`;
  return (
    <>
      <path d={arc} fill="none" stroke={thread} strokeWidth={1.2} opacity={0.5} />
      {MOON_BEADS.map((b) => (
        <Bead key={`${b.x}-${b.y}`} {...b} />
      ))}
      <line x1={62} y1={30} x2={62} y2={47} stroke={thread} strokeWidth={1} opacity={0.55} />
      <path d={starPath(62, 54, 7)} fill={BEAD.amber} />
    </>
  );
}

/** The mark alone (header on small screens, the chat bubble, Luna's avatar). */
export function LogoMark({ className, thread = "currentColor" }: { className?: string; thread?: string }) {
  return (
    <svg viewBox="0 0 100 100" className={className} aria-hidden="true">
      <MoonStrand thread={thread} />
    </svg>
  );
}

/** Mark plus wordmark. Inherits its text color from the surrounding element. */
export function Logo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 360 100" className={className} role="img" aria-label="Hilda & Luna Beadworks">
      <MoonStrand thread="currentColor" />
      <text
        x={112}
        y={54}
        fill="currentColor"
        className="font-display"
        fontSize={34}
        fontWeight={600}
        style={{ fontVariationSettings: "'SOFT' 50, 'WONK' 1" }}
      >
        Hilda <tspan fill={BEAD.amber}>&amp;</tspan> Luna
      </text>
      <text x={114} y={76} fill="currentColor" opacity={0.7} fontSize={11.5} fontWeight={600} letterSpacing={4.2}>
        BEADWORKS
      </text>
    </svg>
  );
}
