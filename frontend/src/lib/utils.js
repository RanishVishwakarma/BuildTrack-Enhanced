export function cn(...classes) {
  return classes.filter(Boolean).join(" ");
}

export function getId(item) {
  return item?.id || item?._id;
}

export function formatCurrency(value) {
  if (value == null || value === "" || Number.isNaN(Number(value))) return "Not set";
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(Number(value));
}

export function formatNumber(value) {
  if (value == null || value === "" || Number.isNaN(Number(value))) return "0";
  return new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 }).format(Number(value));
}

export function formatDate(value) {
  if (!value) return "Not set";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat("en-IN", { day: "2-digit", month: "short", year: "numeric" }).format(date);
}

export function formatDateTime(value) {
  if (!value) return "Not set";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat("en-IN", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }).format(date);
}

export function formatStatus(value) {
  if (value === null || value === undefined || value === "") return "Unknown";
  return String(value).replace(/_/g, " ").toLowerCase().replace(/\b\w/g, (char) => char.toUpperCase());
}

// yyyy-mm-dd for <input type="date">, in local time.
export function toDateInput(value) {
  const date = value ? new Date(value) : new Date();
  if (Number.isNaN(date.getTime())) return "";
  const offset = date.getTimezoneOffset() * 60000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 10);
}

export function addDays(days, from = new Date()) {
  const date = new Date(from);
  date.setDate(date.getDate() + days);
  return toDateInput(date);
}

// <input type="date"> value -> ISO datetime the FastAPI models accept.
export function dateInputToIso(value) {
  if (!value) return undefined;
  const date = new Date(`${value}T00:00:00`);
  return Number.isNaN(date.getTime()) ? undefined : date.toISOString();
}

export function normalizeList(response) {
  if (Array.isArray(response)) return { items: response, total: response.length };
  if (Array.isArray(response?.items)) return { items: response.items, total: response.total ?? response.items.length };
  return { items: [], total: 0 };
}

// Label for a reference whose record isn't in the loaded lookup list, so the UI
// never shows a raw database id. Usually the record was deleted.
export function missingRecord(kind, { loading, error } = {}) {
  if (loading) return "Loading...";
  if (error) return `${kind} unavailable`;
  return `Deleted ${kind.toLowerCase()}`;
}

export function workerName(worker) {
  if (!worker) return "";
  return worker.name || [worker.first_name, worker.last_name].filter(Boolean).join(" ") || worker.worker_code || worker.email || "Unnamed worker";
}

export function projectName(project) {
  return project?.name || project?.project_name || "Unnamed project";
}

export function matchesSearch(values, query) {
  const text = query.trim().toLowerCase();
  if (!text) return true;
  return values.filter((value) => value !== null && value !== undefined).join(" ").toLowerCase().includes(text);
}

export function downloadCsv(filename, rows) {
  const csv = rows.map((row) => row.map((cell) => `"${String(cell ?? "").replace(/"/g, '""')}"`).join(",")).join("\n");
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
