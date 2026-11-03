export type CameraAction = "explore" | "overview" | "x-" | "x+" | "y-" | "y+" | "z-" | "z+";
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
  return <div className="camera-console" aria-label="3D camera controls">
    <div className="camera-presets">
      <button disabled={props.disabled} aria-pressed={props.exploring} onClick={() => props.onAction("explore")}>Explore 2.5×</button>
      <button disabled={props.disabled} aria-pressed={!props.exploring} onClick={() => props.onAction("overview")}>Full city</button>
    </div>
    <details>
      <summary>Turn the camera</summary>
      <p>Drag to {props.pan ? "pan" : "orbit"}. Pinch or scroll to zoom. X tilts, Y turns around the city, Z rolls the view.</p>
      <div className="camera-axes">
        {([['x', 'Tilt'], ['y', 'Turn'], ['z', 'Roll']] as const).map(([axis, label]) =>
          <div key={axis} role="group" aria-label={`${label} camera (${axis.toUpperCase()} axis)`}>
            <span>{axis.toUpperCase()} · {label}</span>
            <button disabled={props.disabled} aria-label={`${label} camera negative`} onClick={() => props.onAction(`${axis}-`)}>−</button>
            <button disabled={props.disabled} aria-label={`${label} camera positive`} onClick={() => props.onAction(`${axis}+`)}>+</button>
          </div>)}
      </div>
      <label><input type="checkbox" checked={props.pan} disabled={props.disabled} onChange={e => props.onPan(e.target.checked)} />Drag to pan instead of orbit</label>
      <label><input type="checkbox" checked={props.cutaway} disabled={props.disabled || props.occluderCount === 0} onChange={e => props.onCutaway(e.target.checked)} />Reveal streets behind foreground buildings</label>
      {props.occluderCount === 0 && <p>This asset has no separately identified buildings. Cutaway is unavailable; the city remains opaque.</p>}
      <p>Cutaway affects the view only. Streets, signals and simulation remain unchanged. Keyboard: X/Y/Z turn; Shift reverses. 0 restores Full city.</p>
    </details>
  </div>;
}
