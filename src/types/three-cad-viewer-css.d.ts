// three-cad-viewer ships its stylesheet as a bare `./css` export (no `.css`
// suffix), so Vite's `*.css` ambient module doesn't cover it and TS can't type a
// side-effect import of it. Declare the subpath as styles-only.
declare module 'three-cad-viewer/css'
