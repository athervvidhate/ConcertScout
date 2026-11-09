/** Native animation sequences, with one cancellation boundary per UI journey. */
type Curve = readonly [number, number, number, number];
const cubic = (curve: Curve) => `cubic-bezier(${curve.join(",")})`;

// Motion components take the curves; native animations take their CSS form.
export const EXPO_OUT_CURVE: Curve = [0.16, 1, 0.3, 1];
export const EXPO_IN_OUT_CURVE: Curve = [0.87, 0, 0.13, 1];
export const BACK_OUT_CURVE: Curve = [0.34, 1.56, 0.64, 1];
export const EXPO_OUT = cubic(EXPO_OUT_CURVE);
export const EXPO_IN_OUT = cubic(EXPO_IN_OUT_CURVE);
export const BACK_OUT = cubic(BACK_OUT_CURVE);

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
