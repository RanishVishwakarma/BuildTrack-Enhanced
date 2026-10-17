import { useEffect, useState } from "react";

// Recharts writes colours into SVG attributes, where CSS var() is not reliable,
// so the Graphite tokens are resolved to concrete oklch() values and refreshed
// whenever the light/dark class on <html> changes.
function read(name) {
  if (typeof window === "undefined") return "";
  const value = getComputedStyle(document.documentElement).getPropertyValue(`--${name}`).trim();
  return value ? `oklch(${value})` : "";
}

function build() {
  const colors = {
    chart1: read("chart-1") || "#7a7a7a",
    chart2: read("chart-2") || "#4d7a80",
    chart3: read("chart-3") || "#9a9a9a",
    chart4: read("chart-4") || "#b0b0b0",
    chart5: read("chart-5") || "#c4c4c4",
    success: read("success") || "#3f8a5f",
    warning: read("warning") || "#b07a2a",
    danger: read("destructive") || "#c0392b",
    foreground: read("foreground") || "#444",
    muted: read("muted-foreground") || "#777",
    border: read("border") || "#ddd",
    card: read("card") || "#fff",
  };
  return {
    colors,
    // Ordered series palette for categorical charts.
    series: [colors.chart1, colors.chart2, colors.chart3, colors.chart4, colors.chart5],
    axis: { stroke: colors.border, tick: { fill: colors.muted, fontSize: 12 } },
    grid: colors.border,
    tooltip: {
      contentStyle: { background: colors.card, border: `1px solid ${colors.border}`, borderRadius: 8, color: colors.foreground },
      labelStyle: { color: colors.foreground, fontWeight: 600 },
      itemStyle: { color: colors.foreground },
      cursor: { fill: colors.border, opacity: 0.4 },
    },
    legend: { color: colors.muted, fontSize: 12 },
  };
}

export function useChartTheme() {
  const [theme, setTheme] = useState(build);
  useEffect(() => {
    const observer = new MutationObserver(() => setTheme(build()));
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => observer.disconnect();
  }, []);
  return theme;
}
