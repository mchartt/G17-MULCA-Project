import { useId } from "react";

/**
 * Cadence's mark: a "C" in two violets, redrawn as SVG from Matteo's brand
 * assets (19/11, geometry redone 27/11 to match the brand board). The deep arc is the group's rhythm, the lighter lower lobe
 * is Cadence joining in. Decorative next to the word "Cadence" (aria-hidden),
 * so screen readers read the name once.
 */
export function LogoMark({ size = 28, className }: { size?: number; className?: string }) {
  const id = useId().replace(/:/g, "");
  return (
    <svg className={className} width={size} height={size} viewBox="0 0 64 64" aria-hidden="true" focusable="false">
      <defs>
        <linearGradient id={`${id}-deep`} x1="14" y1="7" x2="38" y2="58" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#8E6CF7" />
          <stop offset=".55" stopColor="#6E52E6" />
          <stop offset="1" stopColor="#4A33C4" />
        </linearGradient>
        <linearGradient id={`${id}-light`} x1="18" y1="38" x2="56" y2="56" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#CDBFFF" />
          <stop offset="1" stopColor="#9C86F6" />
        </linearGradient>
      </defs>
      {/* The deep C: round the left from the slanted upper terminal; the hole sits right of centre. */}
      <path d="M50.92 15.29 A26 26 0 1 0 44.00 54.52 L41.40 38.62 A8.8 8.8 0 1 1 45.16 27.70 Z" fill={`url(#${id}-deep)`} />
      {/* The lighter crescent: from the lower left edge, under the hole, to the rounded tip that lifts to the right. */}
      <path d="M20.65 55.32 Q23.00 45.00 29.38 35.40 A8.8 8.8 0 0 0 45.78 31.61 A5.45 5.45 0 0 1 56.43 29.33 A24.6 24.6 0 0 1 20.65 55.32 Z" fill={`url(#${id}-light)`} />
    </svg>
  );
}

/** The mark and the word, as on the brand board. */
export function Logo({ size = 28, className }: { size?: number; className?: string }) {
  return (
    <span className={`logo${className ? ` ${className}` : ""}`}>
      <LogoMark size={size} />
      <span className="logo__word">Cadence</span>
    </span>
  );
}
