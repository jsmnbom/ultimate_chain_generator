// Ambient type shim for the vendored three-cad-viewer (built from source through
// Vite; see vite.config.ts's alias + tcvHtmlAsString plugin). We deliberately do
// NOT point tsconfig at the submodule's TypeScript source: compiling that whole
// tree under this app's stricter settings (verbatimModuleSyntax, etc.) surfaces
// errors we don't own. Instead this declares just the tiny surface the app uses.
//
// `Display`/`Viewer` instances are held as `any` in Viewer.vue, so only their
// constructors need typing here; the values the app reads off the data/callbacks
// (`Shapes.bb`, the camera fields of a change notification) are typed precisely.
declare module 'three-cad-viewer' {
  export interface BoundingBox {
    xmin: number
    xmax: number
    ymin: number
    ymax: number
    zmin: number
    zmax: number
  }

  // The tessellated shapes tree ocp-tessellate emits and the viewer renders. The
  // app only reads its bounding box (to re-frame the camera on rebuild) and
  // otherwise passes it straight back to the viewer, so keep the rest opaque.
  export interface Shapes {
    bb?: BoundingBox
    [key: string]: unknown
  }

  // One field of a change notification: the viewer reports old/new values.
  export interface Change<T = unknown> {
    new: T
    old?: T
  }

  // Emitted to the notify callback on camera/tool/selection changes. The app only
  // consumes the camera fields (to preserve the view across rebuilds).
  export interface ChangeNotification {
    position?: Change<number[]>
    quaternion?: Change<number[]>
    target?: Change<number[]>
    zoom?: Change<number>
    [key: string]: Change | undefined
  }

  export type NotificationCallback = (change: ChangeNotification) => void

  export class Display {
    constructor(container: HTMLElement, options: Record<string, unknown>)
    glassMode: (enabled: boolean) => void
    showTools: (show: boolean) => void
    setTheme: (theme: string) => void
    dispose?: () => void
  }

  export class Viewer {
    constructor(
      display: Display,
      options: Record<string, unknown>,
      notifyCallback?: NotificationCallback | null,
    )
    [key: string]: unknown
  }

  export const version: string
}
