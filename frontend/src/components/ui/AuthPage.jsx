import { motion, useReducedMotion } from "framer-motion";
import { ChevronLeft } from "lucide-react";
import { useMemo } from "react";
import { Link } from "react-router-dom";
import { Logo } from "../brand/Logo.jsx";
import { Button } from "./Button.jsx";

// Split-screen auth layout adapted from the 21st.dev "auth-page" component:
// a near-black branded panel (the .chrome palette) with white animated paths on
// large screens, and the form on the right. Children supply the heading and form.
export function AuthPage({ children }) {
  return (
    <main className="relative md:h-screen md:overflow-hidden lg:grid lg:grid-cols-2">
      <div className="chrome relative hidden h-full flex-col border-r border-border bg-background p-10 text-foreground lg:flex">
        <div className="absolute inset-0 z-10 bg-gradient-to-t from-background to-transparent" />
        <Brand className="z-10" />
        <div className="z-10 mt-auto">
          <blockquote className="space-y-2">
            <p className="text-xl">
              Projects, crews, materials and procurement in one place, so the office and the site work from the same facts.
            </p>
            <footer className="font-mono text-sm font-semibold">BuildTrack · Site-to-office coordination</footer>
          </blockquote>
        </div>
        <div className="absolute inset-0">
          <FloatingPaths position={1} />
          <FloatingPaths position={-1} />
        </div>
      </div>

      <div className="relative flex min-h-screen flex-col justify-center overflow-y-auto p-4 md:h-screen">
        <div aria-hidden="true" className="absolute inset-0 isolate -z-10 opacity-60 [contain:strict]">
          <div className="absolute right-0 top-0 h-[80rem] w-[35rem] -translate-y-[21.875rem] rounded-full bg-[radial-gradient(68.54%_68.72%_at_55.02%_31.46%,oklch(var(--foreground)/0.06)_0,hsla(0,0%,55%,.02)_50%,oklch(var(--foreground)/0.01)_80%)]" />
          <div className="absolute right-0 top-0 h-[80rem] w-[15rem] rounded-full bg-[radial-gradient(50%_50%_at_50%_50%,oklch(var(--foreground)/0.04)_0,oklch(var(--foreground)/0.01)_80%,transparent_100%)] [translate:5%_-50%]" />
          <div className="absolute right-0 top-0 h-[80rem] w-[15rem] -translate-y-[21.875rem] rounded-full bg-[radial-gradient(50%_50%_at_50%_50%,oklch(var(--foreground)/0.04)_0,oklch(var(--foreground)/0.01)_80%,transparent_100%)]" />
        </div>
        <Button as={Link} className="absolute left-5 top-7" to="/" variant="ghost">
          <ChevronLeft className="size-4" />
          Home
        </Button>
        <div className="mx-auto w-full space-y-4 py-16 sm:w-[24rem]">
          <Brand className="lg:hidden" />
          {children}
        </div>
      </div>
    </main>
  );
}

function Brand({ className = "" }) {
  return <Logo className={className} markClassName="h-10 w-10" textClassName="text-xl" />;
}

export function AuthHeading({ title, description }) {
  return (
    <div className="flex flex-col space-y-1">
      <h1 className="text-2xl font-bold tracking-wide">{title}</h1>
      {description ? <p className="text-base text-muted">{description}</p> : null}
    </div>
  );
}

export function AuthSeparator({ label = "OR" }) {
  return (
    <div className="flex w-full items-center justify-center">
      <div className="h-px w-full bg-border" />
      <span className="shrink-0 whitespace-nowrap px-2 text-xs text-muted">{label}</span>
      <div className="h-px w-full bg-border" />
    </div>
  );
}

function FloatingPaths({ position }) {
  const reduceMotion = useReducedMotion();
  // Durations are fixed per mount so re-renders do not restart the animation.
  const paths = useMemo(
    () =>
      Array.from({ length: 36 }, (_, i) => ({
        id: i,
        d: `M-${380 - i * 5 * position} -${189 + i * 6}C-${380 - i * 5 * position} -${189 + i * 6} -${312 - i * 5 * position} ${216 - i * 6} ${
          152 - i * 5 * position
        } ${343 - i * 6}C${616 - i * 5 * position} ${470 - i * 6} ${684 - i * 5 * position} ${875 - i * 6} ${684 - i * 5 * position} ${875 - i * 6}`,
        width: 0.5 + i * 0.03,
        duration: 20 + Math.random() * 10,
      })),
    [position],
  );

  return (
    <div className="pointer-events-none absolute inset-0">
      <svg className="h-full w-full text-foreground" fill="none" viewBox="0 0 696 316" aria-hidden="true">
        {paths.map((path) =>
          reduceMotion ? (
            <path d={path.d} key={path.id} stroke="currentColor" strokeOpacity={0.1 + path.id * 0.03} strokeWidth={path.width} />
          ) : (
            <motion.path
              animate={{ pathLength: 1, opacity: [0.3, 0.6, 0.3], pathOffset: [0, 1, 0] }}
              d={path.d}
              initial={{ pathLength: 0.3, opacity: 0.6 }}
              key={path.id}
              stroke="currentColor"
              strokeOpacity={0.1 + path.id * 0.03}
              strokeWidth={path.width}
              transition={{ duration: path.duration, repeat: Number.POSITIVE_INFINITY, ease: "linear" }}
            />
          ),
        )}
      </svg>
    </div>
  );
}
