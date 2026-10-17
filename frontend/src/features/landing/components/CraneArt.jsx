import { motion } from "framer-motion";

// Tower-crane line drawing for the landing hero: the structure draws itself
// in, then the hook sways gently. Purely decorative (aria-hidden by caller).
const draw = (delay) => ({
  initial: { pathLength: 0, opacity: 0 },
  animate: { pathLength: 1, opacity: 1 },
  transition: { pathLength: { delay, duration: 2.2, ease: "easeInOut" }, opacity: { delay, duration: 0.3 } },
});

export function CraneArt({ className }) {
  const lattice = Array.from({ length: 11 }, (_, index) => 120 + index * 34);
  return (
    <svg className={className} fill="none" stroke="currentColor" strokeLinecap="round" viewBox="0 0 420 520">
      {/* Mast */}
      <motion.path d="M150 510 V110 M190 510 V110" strokeWidth="2" {...draw(0.4)} />
      {lattice.map((y, index) => (
        <motion.path d={`M150 ${y} L190 ${y + 34} M190 ${y} L150 ${y + 34}`} key={y} strokeOpacity="0.55" strokeWidth="1" {...draw(0.6 + index * 0.06)} />
      ))}
      {/* Jib, counter-jib and ties */}
      <motion.path d="M20 110 H410 M20 92 H410 M150 110 L170 40 L190 110 M170 40 L410 92 M170 40 L20 92" strokeWidth="1.6" {...draw(1.2)} />
      <motion.path d="M30 110 v34 h60 v-34" strokeOpacity="0.7" strokeWidth="1.4" {...draw(1.6)} />
      {/* Cab */}
      <motion.path d="M190 112 h28 v24 h-28" strokeWidth="1.4" {...draw(1.4)} />
      {/* Trolley, cable and hook, swaying from the trolley point */}
      <motion.g
        animate={{ rotate: [-3, 3, -3] }}
        style={{ originX: 0.5, originY: 0 }}
        transition={{ delay: 3, duration: 6, ease: "easeInOut", repeat: Number.POSITIVE_INFINITY }}
      >
        <motion.path d="M330 112 h20 M340 112 V300" strokeWidth="1.2" {...draw(2)} />
        <motion.path d="M340 300 v14 a10 10 0 1 1 -10 10" strokeWidth="2" {...draw(2.6)} />
        <motion.rect animate={{ opacity: 1 }} height="34" initial={{ opacity: 0 }} rx="2" strokeWidth="1.4" transition={{ delay: 3 }} width="56" x="312" y="336" />
      </motion.g>
    </svg>
  );
}
