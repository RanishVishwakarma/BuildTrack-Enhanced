import Lenis from "lenis";
import "lenis/dist/lenis.css";
import { useEffect } from "react";

// Inertial smooth scrolling for the landing page only (Lenis). Anchor links
// glide to their section, landing just below the fixed navbar. Skipped when
// the visitor prefers reduced motion; removed when leaving the page.
export function useSmoothScroll({ headerOffset = 72 } = {}) {
  useEffect(() => {
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return undefined;
    const lenis = new Lenis({
      autoRaf: true,
      lerp: 0.085,
      wheelMultiplier: 0.9,
      anchors: { offset: -headerOffset, duration: 1.4 },
    });
    return () => lenis.destroy();
  }, [headerOffset]);
}
