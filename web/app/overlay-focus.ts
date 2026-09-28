/** Shared modal mechanics; presentation only, never investigation state. */
const FOCUSABLE = "button, input, textarea, select, [href], [tabindex], summary";

export function dialogControls(root: HTMLElement): HTMLElement[] {
  return [...root.querySelectorAll<HTMLElement>(FOCUSABLE)].filter((element) =>
    element.tabIndex >= 0
    && !element.matches(":disabled")
    && !element.closest("[inert], [hidden], [aria-hidden='true']")
    && element.getClientRects().length > 0,
  );
}

export function trapDialogTab(root: HTMLElement, event: KeyboardEvent): void {
  if (event.key !== "Tab") return;
  // Resolve on each keypress: asynchronous configuration and errors can change
  // the dialog's controls after its initial render.
  const controls = dialogControls(root);
  const first = controls[0];
  const last = controls[controls.length - 1];
  const current = root.ownerDocument.activeElement;
  if (!first) {
    event.preventDefault();
    root.focus({ preventScroll: true });
  } else if (!controls.includes(current as HTMLElement)) {
    event.preventDefault();
    (event.shiftKey ? last : first).focus();
  } else if (event.shiftKey && current === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && current === last) {
    event.preventDefault();
    first.focus();
  }
}

export function isolateDialogBackground(cockpit: HTMLElement, dialog: HTMLElement): () => void {
  const changed = [...cockpit.children]
    .filter((node) => node !== dialog && !node.contains(dialog))
    .map((node) => {
      const element = node as HTMLElement;
      const previous = { element, inert: element.inert, ariaHidden: element.getAttribute("aria-hidden") };
      element.inert = true;
      element.setAttribute("aria-hidden", "true");
      return previous;
    });
  return () => {
    for (const { element, inert, ariaHidden } of changed) {
      // Do not clear a state another owner changed while the modal was open.
      if (element.inert) element.inert = inert;
      if (element.getAttribute("aria-hidden") === "true") {
        if (ariaHidden === null) element.removeAttribute("aria-hidden");
        else element.setAttribute("aria-hidden", ariaHidden);
      }
    }
  };
}
