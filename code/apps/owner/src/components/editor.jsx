// What the form inputs share: the settings being edited (draft or live), how to change them,
// and the problems the node reported for the last deploy attempt. Inputs only know a path.
import { createContext, useContext } from "react";
import { getIn } from "../lib/settings.js";

export const EditorContext = createContext(null);

/** `settings`, `set(path, value)`, `update(fn)`, `errors` ({path: message}) and `live` settings. */
export const useEditor = () => useContext(EditorContext);

/** The current value at `path` and the problem reported for it, if any. */
export function useField(path) {
  const { settings, errors } = useEditor();
  return { value: getIn(settings, path), error: errors[path] };
}
