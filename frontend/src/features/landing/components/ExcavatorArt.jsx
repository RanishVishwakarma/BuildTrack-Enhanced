import { motion, useReducedMotion } from "framer-motion";

// Excavator line drawing: draws in when scrolled into view, then the boom and
// arm run a slow digging cycle. Rotations use SVG animateTransform so each
// part pivots around its real joint. Decorative (aria-hidden by caller).
const drawIn = (delay) => ({
  initial: { pathLength: 0, opacity: 0 },
  whileInView: { pathLength: 1, opacity: 1 },
  viewport: { once: true, margin: "-60px" },
  transition: { pathLength: { delay, duration: 1.6, ease: "easeInOut" }, opacity: { delay, duration: 0.3 } },
});

export function ExcavatorArt({ className }) {
  const reduceMotion = useReducedMotion();
  return (
    <svg className={className} fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 420 300">
      {/* Ground and spoil heap */}
      <motion.path d="M0 270 H420 M320 270 q30 -26 70 0" strokeWidth="1.4" {...drawIn(0)} />
      {/* Tracks */}
      <motion.rect height="34" rx="17" strokeWidth="1.8" width="180" x="30" y="232" {...drawIn(0.3)} />
      {[52, 96, 140, 186].map((cx, index) => (
        <motion.circle cx={cx} cy="249" key={cx} r="9" strokeWidth="1.4" {...drawIn(0.5 + index * 0.08)} />
      ))}
      {/* Body and cab */}
      <motion.path d="M48 232 V172 H136 L160 200 H206 V232" strokeWidth="1.8" {...drawIn(0.7)} />
      <motion.path d="M58 182 h46 v26 h-46 z M48 214 h158" strokeWidth="1.2" {...drawIn(0.9)} />
      {/* Boom (pivot at 196,198) carrying the arm (pivot at 290,112) and bucket */}
      <g>
        {!reduceMotion ? (
          <animateTransform attributeName="transform" begin="2.2s" dur="5s" keyTimes="0;0.4;0.7;1" repeatCount="indefinite" type="rotate" values="0 196 198; 9 196 198; -6 196 198; 0 196 198" />
        ) : null}
        <motion.path d="M190 204 L286 104 M202 194 L294 120" strokeWidth="1.8" {...drawIn(1.1)} />
        <g>
          {!reduceMotion ? (
            <animateTransform attributeName="transform" begin="2.2s" dur="5s" keyTimes="0;0.4;0.7;1" repeatCount="indefinite" type="rotate" values="0 290 112; 24 290 112; -10 290 112; 0 290 112" />
          ) : null}
          <motion.path d="M290 112 L326 200" strokeWidth="2" {...drawIn(1.4)} />
          <motion.path d="M318 196 q2 30 34 32 l6 -26 z" strokeWidth="1.8" {...drawIn(1.7)} />
          <motion.path d="M326 226 l-4 8 M338 228 l-2 8 M350 228 l0 8" strokeWidth="1.2" {...drawIn(1.9)} />
        </g>
      </g>
    </svg>
  );
}
