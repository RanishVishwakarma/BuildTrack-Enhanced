import { MeshGradient } from "@paper-design/shaders-react";
import { motion, useReducedMotion } from "framer-motion";

// Full-screen black & white hero with an animated mesh-gradient shader,
// adapted from the 21st.dev "shader-hero" component. Content is passed in:
// `eyebrow` (pill above the title), `title` (letter-by-letter reveal),
// `description`, and `children` for the call-to-action buttons.
const letter = {
  hidden: { opacity: 0, y: 30 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.5 } },
};
const stagger = { hidden: {}, visible: { transition: { staggerChildren: 0.035 } } };

export function ShaderHero({ eyebrow, title, description, children, footer, art, id }) {
  const reduceMotion = useReducedMotion();
  const words = title.split(" ");

  return (
    <section className="relative isolate flex min-h-[100svh] w-full flex-col overflow-hidden bg-black text-white" id={id}>
      <div aria-hidden="true" className="absolute inset-0 -z-10">
        <MeshGradient
          className="absolute inset-0 h-full w-full"
          colors={["#000000", "#1a1a1a", "#2e2e2e", "#ffffff"]}
          distortion={0.8}
          speed={reduceMotion ? 0 : 0.25}
          swirl={0.1}
        />
        <MeshGradient
          className="absolute inset-0 h-full w-full opacity-40 mix-blend-screen"
          colors={["#000000", "#ffffff", "#2e2e2e"]}
          distortion={0.4}
          speed={reduceMotion ? 0 : 0.15}
          swirl={0.6}
        />
        {/* Keeps text legible where the gradient turns white. */}
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,rgba(0,0,0,0.55)_0%,rgba(0,0,0,0.2)_55%,rgba(0,0,0,0.65)_100%)]" />
      </div>
      {/* Optional decorative layer (e.g. line art) between the shader and the content. */}
      {art ? <div aria-hidden="true" className="pointer-events-none absolute inset-0 z-0">{art}</div> : null}

      <div className="relative z-10 mx-auto flex w-full max-w-5xl flex-1 flex-col items-center justify-center px-5 pb-20 pt-32 text-center">
        {eyebrow ? (
          <motion.div
            animate={{ opacity: 1, y: 0 }}
            className="mb-7 flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-4 py-1.5 text-sm font-medium text-white backdrop-blur-lg"
            initial={reduceMotion ? false : { opacity: 0, y: -20 }}
            transition={{ delay: 0.3, duration: 0.8 }}
          >
            {eyebrow}
          </motion.div>
        ) : null}

        <motion.h1
          animate="visible"
          aria-label={title}
          className="flex max-w-4xl flex-wrap justify-center gap-x-[0.25em] font-serif text-5xl font-medium leading-[1.05] tracking-tight text-white drop-shadow-lg md:text-6xl lg:text-7xl"
          initial={reduceMotion ? false : "hidden"}
          variants={stagger}
        >
          {words.map((word, wordIndex) => (
            <span aria-hidden="true" className="inline-flex" key={`${word}-${wordIndex}`}>
              {word.split("").map((char, index) => (
                <motion.span key={index} variants={letter}>
                  {char}
                </motion.span>
              ))}
            </span>
          ))}
        </motion.h1>

        {description ? (
          <motion.p
            animate={{ opacity: 1, y: 0 }}
            className="mt-7 max-w-2xl text-balance text-lg leading-relaxed text-gray-300 md:text-xl"
            initial={reduceMotion ? false : { opacity: 0, y: 20 }}
            transition={{ delay: 1.1, duration: 0.8 }}
          >
            {description}
          </motion.p>
        ) : null}

        {children ? (
          <motion.div
            animate={{ opacity: 1 }}
            className="mt-10 flex flex-wrap items-center justify-center gap-3"
            initial={reduceMotion ? false : { opacity: 0 }}
            transition={{ delay: 1.6, duration: 0.8 }}
          >
            {children}
          </motion.div>
        ) : null}
      </div>
      {footer ? <div className="relative z-10 pb-8">{footer}</div> : null}
    </section>
  );
}
