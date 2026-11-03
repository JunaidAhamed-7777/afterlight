export type CameraAction =
  | "explore"
  | "overview"
  | "x-"
  | "x+"
  | "y-"
  | "y+"
  | "z-"
  | "z+"
  | "zoom-in"
  | "zoom-out";
interface Props {
  exploring: boolean;
  pan: boolean;
  cutaway: boolean;
  occluderCount: number;
  disabled: boolean;
  onAction: (action: CameraAction) => void;
  onPan: (value: boolean) => void;
  onCutaway: (value: boolean) => void;
}
export function CameraControls(props: Props) {
  return (
    <div className="camera-console" aria-label="3D camera controls">
      <div className="camera-presets">
        <button
          disabled={props.disabled}
          aria-pressed={props.exploring}
          onClick={() => props.onAction("explore")}
        >
          Explore
        </button>
        <button
          disabled={props.disabled}
          aria-pressed={!props.exploring}
          onClick={() => props.onAction("overview")}
        >
          Full city
        </button>
      </div>
      <div className="camera-zoom" role="group" aria-label="Map zoom">
        <button
          disabled={props.disabled}
          aria-label="Zoom out"
          onClick={() => props.onAction("zoom-out")}
        >
          −
        </button>
        <span>Zoom</span>
        <button
          disabled={props.disabled}
          aria-label="Zoom in"
          onClick={() => props.onAction("zoom-in")}
        >
          +
        </button>
      </div>
      <details>
        <summary>Camera options</summary>
        <div className="camera-options">
          <p>
            Drag to {props.pan ? "pan" : "orbit"}. Scroll to zoom. Panning
            releases ambulance follow.
          </p>
          <div className="camera-axes">
            {(
              [
                ["x", "Tilt"],
                ["y", "Turn"],
                ["z", "Roll"],
              ] as const
            ).map(([axis, label]) => (
              <div
                key={axis}
                role="group"
                aria-label={`${label} camera (${axis.toUpperCase()} axis)`}
              >
                <span>
                  {axis.toUpperCase()} · {label}
                </span>
                <button
                  disabled={props.disabled}
                  aria-label={`${label} camera negative`}
                  onClick={() => props.onAction(`${axis}-`)}
                >
                  −
                </button>
                <button
                  disabled={props.disabled}
                  aria-label={`${label} camera positive`}
                  onClick={() => props.onAction(`${axis}+`)}
                >
                  +
                </button>
              </div>
            ))}
          </div>
          <label>
            <input
              type="checkbox"
              checked={props.pan}
              disabled={props.disabled}
              onChange={(e) => props.onPan(e.target.checked)}
            />
            Drag to pan instead of orbit
          </label>
          <label>
            <input
              type="checkbox"
              checked={props.cutaway}
              disabled={props.disabled || props.occluderCount === 0}
              onChange={(e) => props.onCutaway(e.target.checked)}
            />
            Reveal streets behind foreground buildings
          </label>
          {props.occluderCount === 0 && (
            <p>
              This asset has no separately identified buildings. Cutaway is
              unavailable; the city remains opaque.
            </p>
          )}
          <p>
            Keyboard: X / Y / Z turn. Shift reverses. 0 restores Full city.
            Focus the map to use shortcuts.
          </p>
        </div>
      </details>
    </div>
  );
}
