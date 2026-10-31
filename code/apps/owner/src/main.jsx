// Entry point of the Tuttie owner view: loads the brand and layout styles and renders the app.
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import "../../shared/tuttie.css";
import "./owner.css";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
