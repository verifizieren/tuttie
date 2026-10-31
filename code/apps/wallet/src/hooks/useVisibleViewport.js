// Keeps the app sized to the part of the screen that is actually visible.
//
// On iOS the on-screen keyboard does not shrink the layout; it pans the whole page up, which
// pushed the wallet off screen. Instead we publish the visual viewport's height and offset as
// CSS variables (--app-h, --app-top, used by .app in wallet.css) and pin the page at the top,
// so the keyboard only makes the app shorter.
import { useEffect } from "react";

export default function useVisibleViewport() {
  useEffect(() => {
    const root = document.documentElement;
    const viewport = window.visualViewport;

    function fit() {
      root.style.setProperty("--app-h", `${viewport ? viewport.height : window.innerHeight}px`);
      root.style.setProperty("--app-top", `${viewport ? viewport.offsetTop : 0}px`);
      window.scrollTo(0, 0);
    }

    fit();
    viewport?.addEventListener("resize", fit);
    viewport?.addEventListener("scroll", fit);
    window.addEventListener("resize", fit);
    return () => {
      viewport?.removeEventListener("resize", fit);
      viewport?.removeEventListener("scroll", fit);
      window.removeEventListener("resize", fit);
    };
  }, []);
}
