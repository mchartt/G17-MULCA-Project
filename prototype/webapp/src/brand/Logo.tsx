import { useId } from "react";

/**
 * Cadence's mark: a "C" in two violets, redrawn as SVG from Matteo's brand
 * assets (19/11). The deep arc is the group's rhythm, the lighter lower lobe
 * is Cadence joining in. Decorative next to the word "Cadence" (aria-hidden),
 * so screen readers read the name once.
 */
export function LogoMark({ size = 28, className }: { size?: number; className?: string }) {
  const id = useId().replace(/:/g, "");
  return (
    <svg className={className} width={size} height={size} viewBox="0 0 64 64" aria-hidden="true" focusable="false">
      <defs>
        <linearGradient id={`${id}-deep`} x1="12" y1="8" x2="44" y2="58" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#8B6CF6" />
          <stop offset=".55" stopColor="#6C5CE7" />
          <stop offset="1" stopColor="#4C35C9" />
        </linearGradient>
        <linearGradient id={`${id}-light`} x1="20" y1="34" x2="54" y2="56" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#C4B5FD" />
          <stop offset="1" stopColor="#A78BFA" />
        </linearGradient>
        <clipPath id={`${id}-disc`}>
          <circle cx="30" cy="32" r="27" />
        </clipPath>
      </defs>
      {/* The deep arc: from the upper terminal, round the left, down to the base. */}
      <path d="M44.7 23.5A17 17 0 1 0 21.5 46.7" fill="none" stroke={`url(#${id}-deep)`} strokeWidth="20" strokeLinecap="round" />
      {/* The lighter lobe: fills the lower half inside the disc, its rounded end under the mouth. */}
      <path clipPath={`url(#${id}-disc)`} d="M31 36H46A8 8 0 0 1 46 52V62H16C18 48 23 38.5 31 36Z" fill={`url(#${id}-light)`} />
      <path d="M31 36H46A8 8 0 0 1 46 52H31Z" fill={`url(#${id}-light)`} />
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
