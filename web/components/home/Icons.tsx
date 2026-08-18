/**
 * The icon set, drawn here.
 *
 * A stock icon library would be a dependency, a bundle, and the single fastest
 * way to make a page look like every other page in the category —
 * `docs/site/DESIGN_SYSTEM.md` §11 refuses it explicitly. These are seven
 * stroked glyphs on a shared 24-grid, and they are all the page needs.
 *
 * Every one is decorative: it sits beside a text label that already carries the
 * meaning, so `aria-hidden` is correct and an `aria-label` would make a screen
 * reader announce the same thing twice.
 */
type IconProps = { size?: number; className?: string };

function Svg({ size = 22, className, children }: IconProps & { children: React.ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      className={className}
    >
      {children}
    </svg>
  );
}

/** A checked mark, for the assurance strip and the aside lists. */
export function IconCheck(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="m8.5 12.2 2.4 2.4 4.6-4.9" />
    </Svg>
  );
}

/** Sun over a roofline — the site's own register. */
export function IconSun(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="11" r="3.6" />
      <path d="M12 3.2v1.8M12 17v1.8M3.6 11h1.8M18.6 11h1.8M6.1 5.1l1.3 1.3M16.6 15.6l1.3 1.3M17.9 5.1l-1.3 1.3M7.4 15.6l-1.3 1.3" />
    </Svg>
  );
}

/** A document with a magnifier: sourced figures. */
export function IconSource(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M13.5 3H6.5A1.5 1.5 0 0 0 5 4.5v15A1.5 1.5 0 0 0 6.5 21h11a1.5 1.5 0 0 0 1.5-1.5V8.5Z" />
      <path d="M13.5 3v5.5H19" />
      <circle cx="11.6" cy="14" r="2.6" />
      <path d="m13.6 16 1.8 1.8" />
    </Svg>
  );
}

/** A question mark inside a frame: stated uncertainty, not hidden. */
export function IconUnknown(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="M9.8 9.4a2.3 2.3 0 0 1 4.4.8c0 1.5-2.2 1.9-2.2 3.3" />
      <path d="M12 17.1h.01" />
    </Svg>
  );
}

/** A shield: consent, and the right to withdraw it. */
export function IconShield(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M12 3 5 5.8v5.4c0 4.3 2.9 8 7 9.3 4.1-1.3 7-5 7-9.3V5.8Z" />
      <path d="m9.2 12 2 2 3.6-3.8" />
    </Svg>
  );
}

/** A house with a roof plane: the project itself. */
export function IconHouse(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M4 10.6 12 4l8 6.6" />
      <path d="M6 9.9V20h12V9.9" />
      <path d="M10 20v-5.2h4V20" />
    </Svg>
  );
}

/** Two people: a person answers, not a machine. */
export function IconPerson(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="8.2" r="3.4" />
      <path d="M5.5 20a6.5 6.5 0 0 1 13 0" />
    </Svg>
  );
}

/** A clipboard with lines: the qualification. */
export function IconClipboard(props: IconProps) {
  return (
    <Svg {...props}>
      <rect x="5" y="4.6" width="14" height="15.4" rx="2" />
      <path d="M9.2 4.6a1 1 0 0 1 1-1h3.6a1 1 0 0 1 1 1v1.2H9.2Z" />
      <path d="M8.8 11.4h6.4M8.8 15h4.2" />
    </Svg>
  );
}
