import { useEffect, useRef, useState } from "react";

/**
 * Shared open/close behavior for every popover on the case audit screen (Figure's
 * manifest popover, InfoTip's bubble) -- closes on a click outside its own DOM node,
 * or Escape. Without this, clicking through several dotted values in a row stacks
 * overlapping popovers with no way to close them except re-clicking each trigger --
 * exactly the exploratory clicking a five-minute reviewer session looks like.
 */
export function useDismissiblePopover<T extends HTMLElement>() {
  const [open, setOpen] = useState(false);
  const ref = useRef<T>(null);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: PointerEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
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
  }, [open]);

  return { open, setOpen, ref };
}
