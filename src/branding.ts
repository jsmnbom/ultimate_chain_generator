// Branding / content config — half of the engine-extraction seam. The engine
// (app shell, worker, ParamForm/Viewer, proto/runtime) reads app identity from
// here and never hardcodes it, so a future adopter swaps this module + the
// `src/designs/` set to reskin the whole playground.
//
//   engineName   — the reusable playground engine (UI chrome / open-source framing)
//   galleryName  — this repo's content brand (the flagship instance)
//   defaultDesign — slug opened when none is specified

export interface BrandLink {
  label: string
  icon: string
  to: string
}

export interface Branding {
  engineName: string
  galleryName: string
  tagline: string
  repoUrl: string
  links: BrandLink[]
  defaultDesign: string
}

const repoUrl = 'https://github.com/jsmnbom/paws-and-parts'

export const branding: Branding = {
  engineName: 'build123d-lab',
  galleryName: 'Paws & Parts',
  tagline: 'A model gallery running on build123d-lab',
  repoUrl,
  links: [{ label: 'GitHub', icon: 'i-lucide-github', to: repoUrl }],
  defaultDesign: 'chain',
}
