// Theme tokens are OKLCH channels defined in src/styles/index.css (Graphite theme).
const token = (name) => `oklch(var(--${name}) / <alpha-value>)`;

export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-sans)"],
        serif: ["var(--font-serif)"],
        mono: ["var(--font-mono)"],
      },
      colors: {
        background: token("background"),
        foreground: token("foreground"),
        // Card / panel surface.
        surface: token("card"),
        card: { DEFAULT: token("card"), foreground: token("card-foreground") },
        popover: { DEFAULT: token("popover"), foreground: token("popover-foreground") },
        primary: { DEFAULT: token("primary"), foreground: token("primary-foreground") },
        secondary: { DEFAULT: token("secondary"), foreground: token("secondary-foreground") },
        accent: { DEFAULT: token("accent"), foreground: token("accent-foreground") },
        // `text-muted` is secondary text; `bg-subtle` is the muted background.
        muted: token("muted-foreground"),
        subtle: token("muted"),
        border: token("border"),
        input: token("input"),
        ring: token("ring"),
        danger: { DEFAULT: token("destructive"), foreground: token("destructive-foreground") },
        success: token("success"),
        warning: token("warning"),
        info: token("info"),
        sidebar: {
          DEFAULT: token("sidebar"),
          foreground: token("sidebar-foreground"),
          primary: token("sidebar-primary"),
          "primary-foreground": token("sidebar-primary-foreground"),
          accent: token("sidebar-accent"),
          "accent-foreground": token("sidebar-accent-foreground"),
          border: token("sidebar-border"),
        },
        chart: {
          1: token("chart-1"),
          2: token("chart-2"),
          3: token("chart-3"),
          4: token("chart-4"),
          5: token("chart-5"),
        },
      },
      borderRadius: {
        xl: "calc(var(--radius) + 4px)",
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      keyframes: {
        marquee: { from: { transform: "translateX(0)" }, to: { transform: "translateX(-50%)" } },
        "page-in": { from: { opacity: "0", transform: "translateY(6px)" }, to: { opacity: "1", transform: "translateY(0)" } },
      },
      animation: {
        marquee: "marquee 40s linear infinite",
        "page-in": "page-in 280ms ease-out both",
      },
      boxShadow: {
        sm: "var(--shadow-sm)",
        DEFAULT: "var(--shadow-sm)",
        md: "var(--shadow-md)",
        lg: "var(--shadow-md)",
        xl: "var(--shadow-xl)",
      },
    },
  },
  plugins: [],
};
