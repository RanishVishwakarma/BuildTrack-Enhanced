// Row of search and filter controls above a table; wraps on small screens.
export function Toolbar({ children }) {
  return <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{children}</div>;
}
