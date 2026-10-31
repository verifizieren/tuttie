// Creates the agent's procedural face on a canvas and keeps it for the component's lifetime.
// Returns a ref to the TuttieFace instance (src/lib/face.js); it starts asleep.
import { useEffect, useRef } from "react";
import TuttieFace from "../lib/face.js";

export default function useFace(canvasRef) {
  const face = useRef(null);

  useEffect(() => {
    face.current = new TuttieFace(canvasRef.current);
    face.current.sleep(0);
    return () => face.current.destroy();
  }, [canvasRef]);

  return face;
}
