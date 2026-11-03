import { useCallback, useEffect, useId, useRef, useState } from "react";
import "./styles/onboarding.css";

export const ONBOARDING_STORAGE_KEY = "afterlight.onboarding.v1";

type TourStatus = "completed" | "skipped";
type Placement = "left" | "right" | "above" | "below";
type Box = { left: number; top: number; width: number; height: number };
type Position = {
  target: Box | null;
  card: Box;
  placement: Placement;
  arrow: number;
};

const steps = [
  {
    selector: ".recording-list",
    title: "Start with a recorded run",
    text: "Pick Cross-city or Westhaven. Each opens a real SUMO run with both traffic worlds ready to compare.",
  },
  {
    selector: ".play-button",
    title: "Press play",
    text: "Play and pause here. The speed menu changes how fast you watch the recording.",
  },
  {
    selector: "#timeline",
    title: "Jump to any moment",
    text: "Drag the timeline to inspect a moment. The clock, traffic and signals stay on the same recorded time.",
  },
  {
    selector: ".follow-controls",
    title: "Stay with the ambulance",
    text: "Follow Ambulance tracks Afterlight; Follow Ghost tracks the ordinary response. Zoom and rotate for a closer look.",
  },
  {
    selector: '.panel-nav [data-tour="results"]',
    title: "Compare the results",
    text: "Open Results to compare response time and the traffic cost. These figures come from the same recorded run.",
  },
] as const;

function hasFinishedTour() {
  try {
    const saved: unknown = JSON.parse(
      localStorage.getItem(ONBOARDING_STORAGE_KEY) ?? "null",
    );
    return (
      typeof saved === "object" &&
      saved !== null &&
      "version" in saved &&
      saved.version === 1 &&
      "status" in saved &&
      (saved.status === "completed" || saved.status === "skipped")
    );
  } catch {
    return false;
  }
}

function visibleBox(element: HTMLElement | null): Box | null {
  if (!element || !element.getClientRects().length) return null;
  const rect = element.getBoundingClientRect();
  let left = Math.max(8, rect.left - 6);
  let top = Math.max(8, rect.top - 6);
  let right = Math.min(innerWidth - 8, rect.right + 6);
  let bottom = Math.min(innerHeight - 8, rect.bottom + 6);
  for (let parent = element.parentElement; parent; parent = parent.parentElement) {
    const style = getComputedStyle(parent);
    const parentRect = parent.getBoundingClientRect();
    if (/auto|scroll|hidden|clip/.test(style.overflowX)) {
      left = Math.max(left, parentRect.left + 2);
      right = Math.min(right, parentRect.right - 2);
    }
    if (/auto|scroll|hidden|clip/.test(style.overflowY)) {
      top = Math.max(top, parentRect.top + 2);
      bottom = Math.min(bottom, parentRect.bottom - 2);
    }
  }
  return right > left && bottom > top
    ? { left, top, width: right - left, height: bottom - top }
    : null;
}

function positionCard(target: Box | null, width: number, height: number): Position {
  const margin = 16;
  const clampX = (n: number) => Math.max(margin, Math.min(n, innerWidth - width - margin));
  const clampY = (n: number) => Math.max(margin, Math.min(n, innerHeight - height - margin));
  if (!target) {
    return {
      target,
      card: { left: clampX((innerWidth - width) / 2), top: clampY((innerHeight - height) / 2), width, height },
      placement: "below",
      arrow: 0,
    };
  }
  const centerX = target.left + target.width / 2;
  const centerY = target.top + target.height / 2;
  const candidates: Record<Placement, Box> = {
    right: { left: target.left + target.width + margin, top: clampY(centerY - height / 2), width, height },
    left: { left: target.left - width - margin, top: clampY(centerY - height / 2), width, height },
    below: { left: clampX(centerX - width / 2), top: target.top + target.height + margin, width, height },
    above: { left: clampX(centerX - width / 2), top: target.top - height - margin, width, height },
  };
  const priority: Placement[] = centerX < innerWidth / 3
    ? ["right", "below", "above", "left"]
    : ["above", "below", "left", "right"];
  const placement = priority.find((side) => {
    const b = candidates[side];
    return b.left >= margin && b.top >= margin && b.left + width <= innerWidth - margin && b.top + height <= innerHeight - margin;
  }) ?? "above";
  const candidate = candidates[placement];
  const card = { ...candidate, left: clampX(candidate.left), top: clampY(candidate.top) };
  const arrow = placement === "left" || placement === "right"
    ? Math.max(24, Math.min(height - 24, centerY - card.top))
    : Math.max(24, Math.min(width - 24, centerX - card.left));
  return { target, card, placement, arrow };
}

export type OnboardingProps = {
  /** The city and first recording are usable, with the loading screen closed. */
  ready: boolean;
  /** Increment from a Settings button to reopen the tour after it was dismissed. */
  openRequest?: number;
  /** The owner can pause playback and reveal Run without changing the recording. */
  onOpen?: () => void;
  onClose?: () => void;
};

export function Onboarding({ ready, openRequest = 0, onOpen, onClose }: OnboardingProps) {
  const [step, setStep] = useState<number | null>(null);
  const [position, setPosition] = useState<Position | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const card = useRef<HTMLDivElement>(null);
  const next = useRef<HTMLButtonElement>(null);
  const previousFocus = useRef<HTMLElement | null>(null);
  const activeTarget = useRef<HTMLElement | null>(null);
  const autoOpened = useRef(false);
  const handledRequest = useRef(0);
  const callbacks = useRef({ onOpen, onClose });
  callbacks.current = { onOpen, onClose };
  const titleId = useId();
  const textId = useId();
  const progressId = useId();
  const open = step !== null;
  const positioned = position !== null;

  const begin = useCallback(() => {
    previousFocus.current = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    setPosition(null);
    setStep(0);
    callbacks.current.onOpen?.();
  }, []);

  useEffect(() => {
    if (!ready) return;
    const requested = openRequest > handledRequest.current;
    handledRequest.current = Math.max(handledRequest.current, openRequest);
    if (requested || (!autoOpened.current && !hasFinishedTour())) {
      autoOpened.current = true;
      begin();
    }
  }, [ready, openRequest, begin]);

  const finish = useCallback((status: TourStatus) => {
    try {
      localStorage.setItem(ONBOARDING_STORAGE_KEY, JSON.stringify({ version: 1, status }));
    } catch {
      // A blocked storage area must not prevent leaving or reopening the tour.
    }
    setStep(null);
    callbacks.current.onClose?.();
  }, []);

  useEffect(() => {
    if (!open || !dialog.current) return;
    const element = dialog.current;
    element.showModal();
    return () => {
      element.close();
      const restore = previousFocus.current;
      const focusableSelector = 'button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),a[href],[tabindex]:not([tabindex="-1"])';
      if (restore?.isConnected && restore.matches(focusableSelector) && restore.getClientRects().length) {
        restore.focus({ preventScroll: true });
      } else {
        const target = activeTarget.current;
        const focusable = target?.matches(focusableSelector)
          ? target
          : target?.querySelector<HTMLElement>(focusableSelector);
        (focusable ?? document.querySelector<HTMLElement>(steps[4].selector))?.focus({ preventScroll: true });
      }
    };
  }, [open]);

  useEffect(() => {
    if (step === null) return;
    const target = document.querySelector<HTMLElement>(steps[step].selector);
    activeTarget.current = target;
    target?.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "instant" });
    let frame = 0;
    const update = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        if (!card.current) return;
        const bounds = card.current.getBoundingClientRect();
        setPosition(positionCard(visibleBox(target), bounds.width, bounds.height));
      });
    };
    const observer = new ResizeObserver(update);
    if (target) observer.observe(target);
    if (card.current) observer.observe(card.current);
    addEventListener("resize", update);
    document.addEventListener("scroll", update, true);
    update();
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      removeEventListener("resize", update);
      document.removeEventListener("scroll", update, true);
    };
  }, [step]);

  useEffect(() => {
    if (open && positioned) next.current?.focus({ preventScroll: true });
  }, [step, open, positioned]);

  if (step === null) return null;
  const current = steps[step];
  const final = step === steps.length - 1;
  return (
    <dialog
      ref={dialog}
      className="onboarding-layer"
      aria-labelledby={titleId}
      aria-describedby={`${progressId} ${textId}`}
      aria-modal="true"
      onCancel={(event) => {
        event.preventDefault();
        finish("skipped");
      }}
      data-step={step + 1}
      data-target={current.selector}
    >
      {position?.target ? (
        <div className="onboarding-spotlight" aria-hidden="true" style={position.target} />
      ) : (
        <div className="onboarding-dim" aria-hidden="true" />
      )}
      <div
        ref={card}
        className="onboarding-card"
        data-placement={position?.placement}
        style={{
          left: position?.card.left ?? 16,
          top: position?.card.top ?? 16,
          visibility: position ? "visible" : "hidden",
        }}
      >
        {position?.target && (
          <span
            className="onboarding-arrow"
            aria-hidden="true"
            style={position.placement === "left" || position.placement === "right"
              ? { top: position.arrow }
              : { left: position.arrow }}
          />
        )}
        <div aria-live="polite" aria-atomic="true">
          <div className="onboarding-meta">
            <span>A quick look</span>
            <span id={progressId}>{step + 1} of {steps.length}</span>
          </div>
          <h2 id={titleId}>{current.title}</h2>
          <p id={textId}>{current.text}</p>
        </div>
        <div className="onboarding-actions">
          <button className="onboarding-skip" onClick={() => finish("skipped")}>Skip tour</button>
          <div>
            <button disabled={step === 0} onClick={() => setStep(step - 1)}>Back</button>
            <button ref={next} className="onboarding-next" onClick={() => final ? finish("completed") : setStep(step + 1)}>
              {final ? "Done" : "Next"}
              {!final && <span aria-hidden="true">→</span>}
            </button>
          </div>
        </div>
      </div>
    </dialog>
  );
}
