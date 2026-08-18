/**
 * The hero composition.
 *
 * Drawn here rather than loaded, for four reasons recorded in
 * `docs/site/DESIGN_SYSTEM.md` §7: the CSP is `img-src 'self' data:` so nothing
 * remote could load anyway; a vector is a few kilobytes against a photograph's
 * hundreds; an inline SVG costs no round trip and so cannot delay LCP; and it
 * carries no licence risk and cannot be a stock cliché.
 *
 * The subject is a Belgian/Dutch detached house — brick body, steep gable, a
 * modern all-black array — because that is the housing stock this site is
 * addressed to. It is honestly illustrative: it does not claim to be a
 * photograph of an installation this business performed, which is the line a
 * generated "photo" of a house that does not exist would cross.
 *
 * The roof is built from two parallelograms sharing a vertical ridge, and the
 * panels are laid out by interpolating across the sunward one. Placing them by
 * hand is what made the first attempt read as a dark smear instead of an array:
 * the panel edges have to follow the rake exactly or the eye refuses the plane.
 */

/** Ridge apex, the two eaves, and the depth the roof planes are given. */
const APEX = { x: 500, y: 176 };
const EAVE_L = { x: 286, y: 330 };
const EAVE_R = { x: 714, y: 330 };
const DEPTH = 74;

type Pt = { x: number; y: number };

const quad = (p: Pt[]) => p.map((q) => `${q.x.toFixed(1)},${q.y.toFixed(1)}`).join(" ");

/**
 * A point on a roof plane in (rake, depth) coordinates, both 0…1.
 * `s` runs from the ridge down the rake to the eave; `t` runs down the slope.
 */
function onPlane(eave: Pt, s: number, t: number): Pt {
  return {
    x: APEX.x + (eave.x - APEX.x) * s,
    y: APEX.y + (eave.y - APEX.y) * s + DEPTH * t,
  };
}

/** The sunward plane's array: six columns, two rows, with a hairline gutter. */
function panels() {
  const cols = 6;
  const rows = 2;
  const s0 = 0.1;
  const s1 = 0.94;
  const t0 = 0.12;
  const t1 = 0.9;
  const gap = 0.012;
  const out: { key: string; body: string; sheen: string; split: string }[] = [];

  for (let c = 0; c < cols; c += 1) {
    for (let r = 0; r < rows; r += 1) {
      const sa = s0 + ((s1 - s0) * c) / cols + gap;
      const sb = s0 + ((s1 - s0) * (c + 1)) / cols - gap;
      const ta = t0 + ((t1 - t0) * r) / rows + gap;
      const tb = t0 + ((t1 - t0) * (r + 1)) / rows - gap;
      const a = onPlane(EAVE_R, sa, ta);
      const b = onPlane(EAVE_R, sb, ta);
      const d = onPlane(EAVE_R, sb, tb);
      const e = onPlane(EAVE_R, sa, tb);
      const mid = (p: Pt, q: Pt, f: number) => ({
        x: p.x + (q.x - p.x) * f,
        y: p.y + (q.y - p.y) * f,
      });
      out.push({
        key: `${c}-${r}`,
        body: quad([a, b, d, e]),
        sheen: quad([a, b, mid(b, d, 0.42), mid(a, e, 0.42)]),
        split: quad([mid(a, b, 0.5), mid(e, d, 0.5)]),
      });
    }
  }
  return out;
}

export function HeroVisual() {
  const roofLeft = [
    APEX,
    EAVE_L,
    { x: EAVE_L.x, y: EAVE_L.y + DEPTH },
    { x: APEX.x, y: APEX.y + DEPTH },
  ];
  const roofRight = [
    APEX,
    EAVE_R,
    { x: EAVE_R.x, y: EAVE_R.y + DEPTH },
    { x: APEX.x, y: APEX.y + DEPTH },
  ];

  return (
    <svg
      viewBox="0 0 800 560"
      role="img"
      aria-labelledby="hero-visual-title"
      xmlns="http://www.w3.org/2000/svg"
    >
      <title id="hero-visual-title">
        Illustration d&apos;une maison individuelle en brique, à toiture inclinée,
        dont le pan exposé au soleil porte un ensemble de panneaux
        photovoltaïques.
      </title>

      <defs>
        <linearGradient id="mps-sky" x1="0" y1="0" x2="0.25" y2="1">
          <stop offset="0%" stopColor="#cfe7f2" />
          <stop offset="52%" stopColor="#e6f2ee" />
          <stop offset="100%" stopColor="#fdf6e9" />
        </linearGradient>
        <linearGradient id="mps-panel" x1="0" y1="0" x2="0.6" y2="1">
          <stop offset="0%" stopColor="#2b4653" />
          <stop offset="100%" stopColor="#0e1b22" />
        </linearGradient>
        <linearGradient id="mps-sheen" x1="0" y1="0" x2="0.7" y2="1">
          <stop offset="0%" stopColor="#ffffff" stopOpacity="0.30" />
          <stop offset="100%" stopColor="#ffffff" stopOpacity="0.03" />
        </linearGradient>
        <linearGradient id="mps-brick" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#f3e6da" />
          <stop offset="100%" stopColor="#e6d4c4" />
        </linearGradient>
        <radialGradient id="mps-sunglow" cx="0.5" cy="0.5" r="0.5">
          <stop offset="0%" stopColor="#f7c352" stopOpacity="0.55" />
          <stop offset="100%" stopColor="#f7c352" stopOpacity="0" />
        </radialGradient>
        <clipPath id="mps-frame">
          <rect x="0" y="0" width="800" height="560" />
        </clipPath>
      </defs>

      <g clipPath="url(#mps-frame)">
        <rect width="800" height="560" fill="url(#mps-sky)" />

        {/* Morning sun, low and warm rather than a flat disc */}
        <circle cx="662" cy="112" r="96" fill="url(#mps-sunglow)" />
        <circle cx="662" cy="112" r="27" fill="#f7bb45" />

        {/* Distant rooflines: depth without detail */}
        <g fill="#c3dad4" opacity="0.6">
          <path d="M0 400 L62 352 L124 400 L124 442 L0 442 Z" />
          <path d="M124 418 L172 384 L220 418 L220 442 L124 442 Z" />
          <path d="M700 404 L752 366 L800 404 L800 442 L700 442 Z" />
        </g>

        {/* Ground */}
        <rect x="0" y="438" width="800" height="122" fill="#e4efe8" />
        <rect x="0" y="438" width="800" height="4" fill="#cfe0d7" />

        {/* Neighbouring house, left — establishes a street */}
        <path d="M96 442 L96 336 L176 282 L256 336 L256 442 Z" fill="#e8dbcf" />
        <path d="M84 340 L176 278 L268 340 L258 352 L176 292 L94 352 Z" fill="#cdbaab" />
        <rect x="126" y="366" width="34" height="40" rx="3" fill="#f7fbf9" stroke="#cdbaab" strokeWidth="3" />
        <rect x="192" y="366" width="34" height="40" rx="3" fill="#f7fbf9" stroke="#cdbaab" strokeWidth="3" />

        {/* ── The subject house ─────────────────────────────────────────── */}

        {/* Brick body */}
        <rect x="318" y="330" width="364" height="112" fill="url(#mps-brick)" />
        {/* Gable wall, above the eaves and behind the roof planes */}
        <path d="M500 190 L676 316 L324 316 Z" fill="#efe1d4" />

        {/* Chimney, behind the ridge */}
        <rect x="600" y="212" width="30" height="66" rx="3" fill="#d8c5b4" />
        <rect x="594" y="206" width="42" height="12" rx="3" fill="#c8b3a1" />

        {/* Roof planes. Left is the shaded side, right faces the sun. */}
        <polygon points={quad(roofLeft)} fill="#8d5a45" />
        <polygon points={quad(roofRight)} fill="#a06d54" />
        {/* Ridge and eave lines, so the planes read as planes */}
        <path
          d={`M${APEX.x} ${APEX.y} L${APEX.x} ${APEX.y + DEPTH}`}
          stroke="#754737"
          strokeWidth="2.5"
        />
        <path
          d={`M${EAVE_L.x - 12} ${EAVE_L.y + DEPTH} L${APEX.x} ${APEX.y + DEPTH} L${EAVE_R.x + 12} ${EAVE_R.y + DEPTH}`}
          stroke="#754737"
          strokeWidth="7"
          strokeLinejoin="round"
          fill="none"
        />

        {/* The array, on the sunward plane */}
        <g>
          {panels().map((p) => (
            <g key={p.key}>
              <polygon points={p.body} fill="url(#mps-panel)" stroke="#0a1418" strokeWidth="1.4" />
              <polygon points={p.sheen} fill="url(#mps-sheen)" />
              <polyline points={p.split} fill="none" stroke="#3d5c6a" strokeWidth="0.8" opacity="0.55" />
            </g>
          ))}
        </g>

        {/* Gable window */}
        <rect x="474" y="238" width="52" height="40" rx="4" fill="#f8fcfa" stroke="#d3c0b0" strokeWidth="3" />
        <path d="M500 238v40M474 258h52" stroke="#d3c0b0" strokeWidth="2.5" />

        {/* Ground-floor openings */}
        <rect x="352" y="356" width="62" height="62" rx="4" fill="#f8fcfa" stroke="#d0bcac" strokeWidth="3.5" />
        <path d="M383 356v62M352 387h62" stroke="#d0bcac" strokeWidth="2.5" />
        <rect x="586" y="356" width="62" height="62" rx="4" fill="#f8fcfa" stroke="#d0bcac" strokeWidth="3.5" />
        <path d="M617 356v62M586 387h62" stroke="#d0bcac" strokeWidth="2.5" />
        <rect x="466" y="352" width="68" height="90" rx="5" fill="#0f6b4f" />
        <rect x="478" y="364" width="44" height="28" rx="3" fill="#e8f3ee" opacity="0.9" />
        <circle cx="522" cy="410" r="4" fill="#f7bb45" />

        {/* Inverter: the unglamorous box that makes it an installation */}
        <rect x="694" y="368" width="28" height="40" rx="4" fill="#f7fbf9" stroke="#c1d3cb" strokeWidth="3" />
        <path d="M700 380h16M700 390h11" stroke="#9db4ab" strokeWidth="3" strokeLinecap="round" />

        {/* Planting: two masses, not a hedge of clip art */}
        <path d="M44 442 C44 392 78 366 110 366 C142 366 176 392 176 442 Z" fill="#2f7d5e" />
        <path d="M110 442 V378" stroke="#20604a" strokeWidth="6" strokeLinecap="round" />
        <path d="M746 442 C746 410 766 392 786 392 C806 392 812 410 812 442 Z" fill="#2f7d5e" opacity="0.75" />
        <ellipse cx="268" cy="436" rx="46" ry="16" fill="#3d8f6d" opacity="0.5" />
        <ellipse cx="742" cy="438" rx="52" ry="14" fill="#3d8f6d" opacity="0.35" />

        {/* Foreground: plants the house in a place and crops the base */}
        <path
          d="M0 442 C96 430 158 448 252 440 C346 432 434 450 534 442 C634 434 706 450 800 440 L800 560 L0 560 Z"
          fill="#dcebe2"
        />
        <path
          d="M0 486 C120 478 214 494 320 486 C426 478 520 496 640 486 C712 480 762 486 800 484 L800 560 L0 560 Z"
          fill="#cfe3d7"
          opacity="0.75"
        />
      </g>
    </svg>
  );
}
