import { useLayoutEffect, useState, type RefObject } from "react";

export interface PopoverPosition {
  top: number;
  left: number;
  // How tall the popover is allowed to get before it must scroll internally, given
  // where it actually landed. A CSS max-height alone (e.g. `min(70vh, 100vh - 24px)`)
  // caps the popover's OWN height but has no idea how far down the viewport `top`
  // already is -- a trigger a few hundred pixels down the page still overflows off
  // the bottom of the window even with that cap, because the cap never subtracted
  // `top`. This does, so the popover's bottom edge never goes past the window.
  maxHeight: number;
}

/**
 * Fixed-viewport coordinates for a popover rendered via a React portal (see
 * Figure.tsx / InfoTip.tsx) -- exists because `position: absolute` relative to the
 * trigger only works while the popover is a DOM descendant of it. An ancestor with
 * ANY non-`none` computed `transform` (including a settled, visually-identity one
 * left behind by `animation-fill-mode: forwards` -- see DecisionStep.css's `.step`,
 * confirmed live via `document.elementFromPoint()` landing on the wrong element, not
 * assumed from reading the CSS) creates its own stacking context, and no z-index
 * value on a descendant can escape it. A raised z-index never fixes this -- only
 * rendering outside the trapping ancestor does. `position: fixed` + coordinates
 * computed here, from the actual trigger element, is that escape.
 *
 * Recomputed on open, and on every scroll/resize while open, so the popover tracks
 * its trigger instead of drifting off it -- including under browser zoom, which
 * changes layout metrics without firing a dedicated event of its own but does fire
 * `resize`.
 */
export function usePopoverPosition(
  triggerRef: RefObject<HTMLElement | null>,
  open: boolean,
  options?: { placement?: "bottom-start" | "top-center"; gap?: number; estimatedWidth?: number },
): PopoverPosition | null {
  const [position, setPosition] = useState<PopoverPosition | null>(null);
  const placement = options?.placement ?? "bottom-start";
  const gap = options?.gap ?? 4;
  const estimatedWidth = options?.estimatedWidth ?? 320;

  // oxlint's react/set-state-in-effect flags synchronous setState in an effect on
  // the general principle that it usually means "derive this during render instead."
  // Doesn't apply here: a trigger's real screen position doesn't exist until AFTER
  // layout, which is exactly what useLayoutEffect (not useEffect) is for -- there is
  // no render-time value to derive this from, only a DOM measurement taken after paint.
  useLayoutEffect(() => {
    if (!open) {
      // oxlint-disable-next-line react/set-state-in-effect -- see comment above
      setPosition(null);
      return;
    }

    const recompute = () => {
      const el = triggerRef.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      const margin = 8; // keeps the popover from touching the viewport edge at 150%+ zoom

      let top: number;
      let left: number;
      if (placement === "top-center") {
        top = rect.top - gap; // caller offsets further by the popover's own height via CSS transform
        left = rect.left + rect.width / 2;
      } else {
        top = rect.bottom + gap;
        left = rect.left;
      }

      // Clamp horizontally so a trigger near the right edge (a wide viewport's last
      // column, or any width at 150% zoom) never pushes the popover off-screen --
      // exactly the kind of thing "raise the z-index and hope" never catches.
      const maxLeft = window.innerWidth - estimatedWidth - margin;
      left = Math.max(margin, Math.min(left, maxLeft));
      top = Math.max(margin, top);

      // Whatever's left between `top` and the bottom of the window, minus a margin --
      // recomputed on every scroll/resize just like top/left, so it stays correct as
      // the trigger's on-screen position changes. Also capped at 70% of the viewport
      // even when there's technically more room below a trigger near the top of a
      // tall page -- a popover that tall reads as its own separate page, not a
      // provenance card. Below that ceiling, the true constraint is "don't run past
      // the window's actual bottom edge," not a fixed vh value on its own.
      const maxHeight = Math.max(120, Math.min(window.innerHeight - top - margin, window.innerHeight * 0.7));

      setPosition({ top, left, maxHeight });
    };

    recompute();
    window.addEventListener("scroll", recompute, true);
    window.addEventListener("resize", recompute);
    return () => {
      window.removeEventListener("scroll", recompute, true);
      window.removeEventListener("resize", recompute);
    };
  }, [open, triggerRef, placement, gap, estimatedWidth]);

  return position;
}
