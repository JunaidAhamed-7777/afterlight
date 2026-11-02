import { Component, type ReactNode } from "react";
/** A lazy-renderer/module failure must never remove the accessible evidence panel. */
export class CanvasBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? (
      <div className="city-view">
        <img
          className="city-fallback"
          src={`${import.meta.env.BASE_URL}assets/previews/city_overview.png`}
          alt="Original city authoring preview; 3D renderer unavailable"
        />
        <div className="canvas-status" role="alert">
          <p>
            The 3D viewer could not start. The recording evidence below remains
            available.
          </p>
          <button onClick={() => location.reload()}>Reload viewer</button>
        </div>
      </div>
    ) : (
      this.props.children
    );
  }
}
