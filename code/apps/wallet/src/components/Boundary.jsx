// A safety net around what Tuttie shows: if one part fails to render (say an old conversation
// from the history in a shape this version does not expect), only that part is replaced by a
// short note (`message`, in a box with `className`); the wallet, the face and the dock keep
// working. A part that must still offer a way out (the approval sheet) passes `fallback`, which
// is rendered instead of the note. React needs a class for this.
import { Component } from "react";

export default class Boundary extends Component {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error) {
    console.error("Wallet view failed to render:", error);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    if (this.props.fallback) return this.props.fallback;
    return <div className={this.props.className || "activity"}><div className="bubble tuttie"><p>{this.props.message}</p></div></div>;
  }
}
