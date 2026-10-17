import { motion } from "framer-motion";

// Building under construction: floors rise one by one from the ground,
// scaffolding follows, then windows light up. Decorative (aria-hidden by caller).
const FLOORS = 7;
const FLOOR_HEIGHT = 56;
const BASE = 500;

export function BuildingArt({ className }) {
  const floors = Array.from({ length: FLOORS }, (_, index) => BASE - (index + 1) * FLOOR_HEIGHT);
  return (
    <svg className={className} fill="none" stroke="currentColor" strokeLinecap="round" viewBox="0 0 360 520">
      {/* Ground line */}
      <motion.path animate={{ pathLength: 1 }} d="M0 500 H360" initial={{ pathLength: 0 }} strokeWidth="1.6" transition={{ duration: 1.2, ease: "easeInOut" }} />
      {/* Floors stack upward */}
      {floors.map((y, index) => (
        <motion.g
          animate={{ opacity: 1, y: 0 }}
          initial={{ opacity: 0, y: 18 }}
          key={y}
          transition={{ delay: 0.6 + index * 0.35, duration: 0.6, ease: "easeOut" }}
        >
          <rect height={FLOOR_HEIGHT} strokeWidth="1.5" width="200" x="60" y={y} />
          {[80, 120, 160, 200, 240].map((x) => (
            <motion.rect
              animate={{ opacity: [0, 0.9, 0.35] }}
              fill="currentColor"
              fillOpacity="0.35"
              height="22"
              initial={{ opacity: 0 }}
              key={x}
              strokeWidth="0.8"
              transition={{ delay: 3.4 + index * 0.15 + x / 400, duration: 1.4 }}
              width="18"
              x={x}
              y={y + 17}
            />
          ))}
        </motion.g>
      ))}
      {/* Scaffolding on the right face */}
      <motion.path
        animate={{ pathLength: 1, opacity: 0.6 }}
        d={`M262 500 V${BASE - FLOORS * FLOOR_HEIGHT - 20} M292 500 V${BASE - FLOORS * FLOOR_HEIGHT - 20} ${floors
          .map((y) => `M262 ${y} H292 M262 ${y + FLOOR_HEIGHT} L292 ${y}`)
          .join(" ")}`}
        initial={{ pathLength: 0, opacity: 0 }}
        strokeWidth="1"
        transition={{ delay: 2.2, duration: 2.4, ease: "easeInOut" }}
      />
      {/* Unfinished top: column stubs waiting for the next floor */}
      <motion.path
        animate={{ opacity: [0, 1, 0.4, 1] }}
        d={`M60 ${floors.at(-1)} v-26 M110 ${floors.at(-1)} v-26 M160 ${floors.at(-1)} v-26 M210 ${floors.at(-1)} v-26 M260 ${floors.at(-1)} v-26`}
        initial={{ opacity: 0 }}
        strokeDasharray="4 4"
        strokeWidth="1.4"
        transition={{ delay: 3.2, duration: 2.4, repeat: Number.POSITIVE_INFINITY, repeatType: "reverse" }}
      />
    </svg>
  );
}
