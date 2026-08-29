/**
 * Dutch-route wrapper.
 *
 * The root layout owns `<html lang>` and renders the site chrome with the
 * default locale — changing that per-request would force every page dynamic
 * and undo the ISR/bfcache work. Until the Dutch content phase restructures
 * the chrome, this nested layout scopes `lang="nl"` onto everything under
 * `/nl`, which is what assistive technology needs to pronounce the form
 * correctly. The header and footer above it deliberately stay French for now;
 * that limitation is documented in the NL form report rather than half-fixed.
 */
export default function DutchLayout({ children }: { children: React.ReactNode }) {
  return <div lang="nl">{children}</div>;
}
