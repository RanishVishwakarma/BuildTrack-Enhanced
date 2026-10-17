import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { findRoute, getBreadcrumbs } from "../app/routeConfig.js";
import { LoadingState } from "../components/common/LoadingState.jsx";
import { Breadcrumbs } from "./Breadcrumbs.jsx";
import { Header } from "./Header.jsx";
import { PageMetaContext } from "./pageMeta.js";
import { Sidebar } from "./Sidebar.jsx";

export function AppLayout() {
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [meta, setMeta] = useState(null);
  const [actionsTarget, setActionsTarget] = useState(null);
  const [hasRefresh, setHasRefresh] = useState(false);
  const refreshRef = useRef(null);
  const route = findRoute(location.pathname);
  const pageMeta = useMemo(
    () => ({ meta, setMeta, actionsTarget, refreshRef, hasRefresh, setHasRefresh }),
    [meta, actionsTarget, hasRefresh],
  );

  useEffect(() => {
    document.title = route ? `${route.title} | BuildTrack` : "BuildTrack";
  }, [route]);

  return (
    <PageMetaContext.Provider value={pageMeta}>
      <div className="min-h-screen bg-subtle lg:flex">
        <div className="sticky top-0 hidden h-screen lg:block">
          <Sidebar collapsed={collapsed} />
        </div>
        {mobileOpen ? (
          <div className="fixed inset-0 z-40 lg:hidden">
            <button className="absolute inset-0 bg-black/50" aria-label="Close navigation" onClick={() => setMobileOpen(false)} />
            <div className="relative h-full w-[248px]">
              <Sidebar onNavigate={() => setMobileOpen(false)} />
            </div>
          </div>
        ) : null}
        <div className="min-w-0 flex-1">
          <Header
            collapsed={collapsed}
            fallbackTitle={route?.title}
            meta={meta}
            onMenuClick={() => setMobileOpen(true)}
            onRefresh={hasRefresh ? () => refreshRef.current?.() : undefined}
            onToggleCollapse={() => setCollapsed((value) => !value)}
          />
          <main className="mx-auto w-full max-w-[1600px] p-4 md:p-6 lg:p-8">
            {/* Page toolbar: breadcrumbs on the left, page actions (portalled by
                PageHeader) on the right. Hidden when a page has neither. */}
            <div className="mb-6 flex flex-wrap items-center justify-between gap-3 [&:not(:has(a,button,nav))]:hidden">
              <Breadcrumbs items={getBreadcrumbs(location.pathname)} />
              <div className="ml-auto" ref={setActionsTarget} />
            </div>
            {/* Keyed by pathname so a route change always mounts a fresh page,
                even when two routes render the same component. */}
            <div className="animate-page-in motion-reduce:animate-none" key={location.pathname}>
              <Suspense fallback={<LoadingState label="Loading page..." />}>
                <Outlet />
              </Suspense>
            </div>
          </main>
        </div>
      </div>
    </PageMetaContext.Provider>
  );
}
