// Build-time replacement for three-cad-viewer's StudioComposer (wired in
// vite.config.ts). The real module is the *only* importer of `postprocessing`
// (~2.7 MB) and `n8ao` (~0.7 MB), pulled in for the Studio mode's PBR /
// post-processing pipeline — a feature this app hides (studioTool: false) and
// does not ship. Swapping in this inert class drops both heavy deps from the
// bundle entirely.
//
// StudioComposer is constructed lazily (only when Studio mode is entered), so in
// normal use this stub is never even instantiated. Should Studio still be reached
// (e.g. via its keyboard shortcut), every method is a no-op, so the viewer falls
// back to a plain render with no post effects instead of throwing. The surface
// below mirrors exactly what StudioManager calls on the composer instance.
class StudioComposer {
  render(_deltaTime?: number): void {}
  setCamera(_camera: unknown): void {}
  setSize(_width: number, _height: number): void {}
  setToneMapping(_mode: unknown, _exposure: number): void {}
  setBackgroundProtect(_color: unknown): void {}
  setAOEnabled(_flag: boolean): void {}
  setAOIntensity(_value: number): void {}
  setShadowMaskEnabled(_enabled: boolean): void {}
  setShadowSoftness(_softness: number): void {}
  setShadowMaskIntensity(_intensity: number): void {}
  dispose(): void {}
}

export { StudioComposer }
