import { createPortal } from "react-dom";
import { usePageActionsTarget, usePageRefresh, usePublishPageMeta } from "../../layouts/pageMeta.js";

// The page title and description are shown in the app navbar (see Header),
// and `onRefresh` powers the navbar's refresh button.
// Action buttons render in the toolbar row beside the breadcrumbs; outside
// the app layout (no toolbar) they fall back to rendering in place.
export function PageHeader({ eyebrow, title, description, action, onRefresh }) {
  usePublishPageMeta({ eyebrow, title, description });
  usePageRefresh(onRefresh);
  const target = usePageActionsTarget();
  if (!action) return null;
  const actions = <div className="flex flex-wrap items-center justify-end gap-2">{action}</div>;
  return target ? createPortal(actions, target) : <div className="mb-6">{actions}</div>;
}
