import "@testing-library/jest-dom/vitest";

// Vitest runs in Node, so we ensure requestAnimationFrame is available for React effects.
if (typeof window !== "undefined" && !window.requestAnimationFrame) {
  window.requestAnimationFrame = (callback: FrameRequestCallback): number => {
    return window.setTimeout(() => callback(performance.now()), 16) as unknown as number;
  };
}

if (typeof window !== "undefined") {
  const prototype = window.HTMLElement?.prototype as { scrollIntoView?: (arg?: unknown) => void };
  if (prototype && !prototype.scrollIntoView) {
    prototype.scrollIntoView = () => {};
  }
}
