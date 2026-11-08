/** Native animation sequences, with one cancellation boundary per UI journey. */
export const EXPO_OUT = "cubic-bezier(.16,1,.3,1)";
export const EXPO_IN_OUT = "cubic-bezier(.87,0,.13,1)";
export const BACK_OUT = "cubic-bezier(.34,1.56,.64,1)";
export const POWER_OUT = "cubic-bezier(.22,.61,.36,1)";

export class Choreography {
  readonly controller = new AbortController();
  private animations = new Set<Animation>();
  get live() {
    return !this.controller.signal.aborted;
  }

  animate(
    element: Element,
    frames: Keyframe[],
    duration: number,
    delay = 0,
    easing = EXPO_OUT,
  ) {
    if (!this.live) return Promise.resolve();
    const animation = element.animate(frames, {
      duration,
      delay,
      easing,
      fill: "both",
    });
    this.animations.add(animation);
    return animation.finished
      .then(() => {
        if (this.live && element.isConnected) {
          try {
            animation.commitStyles();
          } catch {
            /* A removed or hidden element has no frame to retain. */
          }
        }
      })
      .catch(() => {})
      .finally(() => {
        animation.cancel();
        this.animations.delete(animation);
      });
  }

  wait(ms: number) {
    if (!this.live) return Promise.resolve();
    return new Promise<void>((resolve) => {
      const done = () => {
        clearTimeout(timer);
        this.controller.signal.removeEventListener("abort", done);
        resolve();
      };
      const timer = setTimeout(done, ms);
      this.controller.signal.addEventListener("abort", done, { once: true });
    });
  }

  count(to: number, duration: number, update: (value: number) => void) {
    const started = performance.now();
    const frame = (now: number) => {
      if (!this.live) return;
      const t = Math.min(1, (now - started) / duration);
      update(Math.round(to * (1 - Math.pow(1 - t, 3))));
      if (t < 1) requestAnimationFrame(frame);
    };
    update(0);
    requestAnimationFrame(frame);
  }

  cancel() {
    this.controller.abort();
    this.animations.forEach((animation) => animation.cancel());
    this.animations.clear();
  }
}
