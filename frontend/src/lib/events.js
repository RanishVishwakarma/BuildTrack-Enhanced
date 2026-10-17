// Fired after notifications are read/deleted so the header badge refreshes.
export const NOTIFICATIONS_CHANGED = "buildtrack:notifications-changed";

export function emitNotificationsChanged() {
  window.dispatchEvent(new Event(NOTIFICATIONS_CHANGED));
}
