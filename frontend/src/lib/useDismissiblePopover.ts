import { useEffect, useRef, useState } from "react";

/**
 * Shared open/close behavior for every popover on the case audit screen (Figure's
 * manifest popover, InfoTip's bubble) -- closes on a click outside its own DOM node,
 * or Escape. Without this, clicking through several dotted values in a row stacks
 * overlapping popovers with no way to close them except re-clicking each trigger --
 * exactly the exploratory clicking a five-minute reviewer session looks like.
 *
 * `portalRef` is optional: Figure/InfoTip render their actual popover content via a
 * React portal into `document.body` (see usePopoverPosition's docstring for why --
 * an ancestor stacking context traps a normally-positioned popover no z-index can
 * escape), so that content is no longer a DOM descendant of `ref`. Without also
 * checking `portalRef`, every click inside the portaled popover itself would read as
 * "outside" and close it immediately. Left unset, behavior is unchanged from before
 * portals existed -- nothing about InfoTip's non-portal callers (if any remain) breaks.
 */
export function useDismissiblePopover<T extends HTMLElement>(portalRef?: React.RefObject<HTMLElement | null>) {
  const [open, setOpen] = useState(false);
  const ref = useRef<T>(null);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: PointerEvent) => {
      const target = e.target as Node;
      const insideTrigger = ref.current && ref.current.contains(target);
      const insidePortal = portalRef?.current && portalRef.current.contains(target);
      if (!insideTrigger && !insidePortal) setOpen(false);
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open, portalRef]);

  return { open, setOpen, ref };
}
