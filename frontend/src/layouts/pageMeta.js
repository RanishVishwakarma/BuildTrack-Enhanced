import { createContext, useContext, useEffect } from "react";

// Pages publish their heading (eyebrow, title, description) through
// <PageHeader>; the navbar in AppLayout displays it. `actionsTarget` is the
// DOM node in the page toolbar where <PageHeader> portals its action buttons.
// `refreshRef` holds the current page's reload function for the navbar's
// refresh button; `hasRefresh` says whether one is registered.
export const PageMetaContext = createContext({
  meta: null,
  setMeta: () => {},
  actionsTarget: null,
  refreshRef: null,
  hasRefresh: false,
  setHasRefresh: () => {},
});

export function usePageMeta() {
  return useContext(PageMetaContext).meta;
}

export function usePageActionsTarget() {
  return useContext(PageMetaContext).actionsTarget;
}

export function usePublishPageMeta({ eyebrow, title, description }) {
  const { setMeta } = useContext(PageMetaContext);
  useEffect(() => {
    setMeta({ eyebrow, title, description });
    return () => setMeta(null);
  }, [eyebrow, title, description, setMeta]);
}

// Registers the page's reload function with the navbar refresh button while
// the calling component is mounted.
export function usePageRefresh(onRefresh) {
  const { refreshRef, setHasRefresh } = useContext(PageMetaContext);
  useEffect(() => {
    if (!onRefresh || !refreshRef) return undefined;
    refreshRef.current = onRefresh;
    setHasRefresh(true);
    return () => {
      if (refreshRef.current === onRefresh) {
        refreshRef.current = null;
        setHasRefresh(false);
      }
    };
  }, [onRefresh, refreshRef, setHasRefresh]);
}
