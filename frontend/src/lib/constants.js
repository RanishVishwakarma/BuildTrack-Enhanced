import { ROLE } from "./roles.js";

// Roles offered on public registration (backend SELF_REGISTER_ROLES).
// Administrator and Vendor accounts are created by an administrator only.
export const REGISTRATION_ROLES = [
  ROLE.PROJECT_MANAGER,
  ROLE.SITE_ENGINEER,
  ROLE.CONTRACTOR,
  ROLE.WORKER,
  ROLE.CLIENT,
];
