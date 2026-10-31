// Entry point of the Tuttie wallet (a PWA). Loads the brand and layout styles, marks the iOS
// home screen app, registers the service worker and renders the app.
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import "../../shared/tuttie.css";
import "./wallet.css";

// iOS home screen apps report themselves here; wallet.css gives them extra top margin.
if (navigator.standalone) document.documentElement.classList.add("standalone");

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register(`${import.meta.env.BASE_URL}sw.js`).catch(() => {});
}

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
