import { cn } from "../../lib/utils.js";

// BuildTrack logo: a tower crane whose mast forms a "T", lifting floors onto a
// building of stacked chevrons. Structure uses currentColor so the mark adapts
// to its background (white on the matte-black chrome, black on light pages);
// the hook, one floor and "Track" use the brand accent (--brand-accent).

const FLOORS = [24.5, 30.9, 37.3, 43.7, 50.1];
const ACCENT_FLOOR = 2;

function chevron(y) {
  // Roof-like chevron floor: 20 wide, 5 tall, peak 2.6 above the edges.
  return `M22 ${y + 2.6} L32 ${y} L42 ${y + 2.6} V${y + 5} L32 ${y + 2.4} L22 ${y + 5} Z`;
}

export function LogoMark({ className, title }) {
  return (
    <svg
      aria-hidden={title ? undefined : "true"}
      className={cn("shrink-0", className)}
      fill="none"
      role={title ? "img" : undefined}
      viewBox="0 0 64 64"
      xmlns="http://www.w3.org/2000/svg"
    >
      {title ? <title>{title}</title> : null}
      {/* Crane: ties, jib, counterweight, mast, base */}
      <path d="M16 8.5 L4.5 18 M16 8.5 L56 18" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" />
      <rect fill="currentColor" height="3" rx="0.6" width="56" x="3" y="17.5" />
      <rect fill="currentColor" height="7" rx="1" width="8" x="1.5" y="16.5" />
      <rect fill="currentColor" height="50" rx="0.8" width="4.2" x="13.9" y="7.5" />
      <rect fill="currentColor" height="4" rx="1" width="44" x="8" y="56" />
      {/* Hook on its cable */}
      <path d="M55.5 20.5 V26" stroke="currentColor" strokeWidth="1.4" />
      <rect fill="var(--brand-accent)" height="3.6" rx="0.7" width="5" x="53" y="26" />
      <path d="M55.5 29.6 v2.4 a2.4 2.4 0 1 1 -2.4 2.4" stroke="var(--brand-accent)" strokeLinecap="round" strokeWidth="1.8" />
      {/* Building: stacked chevron floors and its side wall */}
      <rect fill="currentColor" fillOpacity="0.45" height="26" rx="0.6" width="2.2" x="43" y="30" />
      {FLOORS.map((y, index) => (
        <path d={chevron(y)} fill={index === ACCENT_FLOOR ? "var(--brand-accent)" : "currentColor"} key={y} />
      ))}
    </svg>
  );
}

// Mark + wordmark. `tone` sets the text colour for the context it sits in.
export function Logo({ className, markClassName, textClassName, showText = true }) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <LogoMark className={cn("h-9 w-9", markClassName)} />
      {showText ? (
        <span className={cn("text-lg font-extrabold tracking-tight", textClassName)}>
          Build<span className="text-[var(--brand-accent)]">Track</span>
        </span>
      ) : null}
    </span>
  );
}
