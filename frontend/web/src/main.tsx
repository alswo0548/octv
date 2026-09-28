import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles/style.css";
import "./styles/ui.css";
import "./styles/agency-flow.css";
import "./styles/development.css";
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
import "./styles/refinements.css";
