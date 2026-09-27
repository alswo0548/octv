export type Screen =
  | "login"
  | "signup-basic"
  | "signup-agency"
  | "signup-complete"
  | "home"
  | "incidents"
  | "notifications"
  | "detail"
  | "live"
  | "routes"
  | "request"
  | "settings";
export type Navigate = (screen: Screen, incidentId?: string) => void;
