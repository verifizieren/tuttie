// A double tap on Send (or Enter twice) must not send the same words twice: a second "yes" would
// answer a question the user has not seen yet. Texts still on their way are remembered here.

/** { begin(text) -> false if that text is already being sent, end(text) } */
export function sendGuard() {
  const sending = new Set();
  return {
    begin(text) {
      if (sending.has(text)) return false;
      sending.add(text);
      return true;
    },
    end(text) {
      sending.delete(text);
    },
  };
}
