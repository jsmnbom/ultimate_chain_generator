// The design manifest — the other half of the engine-extraction seam. The engine
// depends only on this interface (slug + source + display metadata), never on a
// specific design's internals. Paws & Parts is just this `src/designs/` set.
//
// Each `src/designs/<slug>/design.py` is bundled as raw source (sent to the
// worker via `reload-design`) and its display metadata is scraped from
// module-level string constants (NAME / AUTHOR / DESCRIPTION), the BLANK flag,
// and the LINKS list (per-design footer links) — co-located with the design so
// they can't drift, and cheap to read without booting Python.

/** A per-design outbound footer link. `icon` is resolved here (see ICON_BY_HOST). */
export interface DesignLink {
  label: string
  url: string
  icon: string
}

export interface DesignMeta {
  /** URL slug and directory name, e.g. "chain" → /m/chain. */
  slug: string
  /** Display name (NAME constant, falls back to the slug). */
  name: string
  author?: string
  description?: string
  /** The verbatim `design.py` source, handed to the worker to build. */
  source: string
  /** Author-provided thumbnail URL, if a `thumb.png` sits in the design dir. */
  thumb?: string
  /** The "start from scratch" starter — rendered distinctly, opens on the Code tab. */
  blank: boolean
  /** Per-design footer links (from the LINKS constant); empty if none declared. */
  links: DesignLink[]
}

// Eager raw-source glob: `../designs/<slug>/design.py` → source string.
const sources = import.meta.glob('./*/design.py', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>

// Optional per-design thumbnail → resolved asset URL.
const thumbs = import.meta.glob('./*/thumb.png', {
  query: '?url',
  import: 'default',
  eager: true,
}) as Record<string, string>

/** Slug (directory name) from a glob key like `./chain/design.py`. */
function slugOf(path: string): string {
  return path.split('/')[1]
}

/** Read a module-level string constant (`NAME = "…"`). */
function pyString(source: string, name: string): string | undefined {
  const m = source.match(new RegExp(`^${name}\\s*=\\s*(['"])([\\s\\S]*?)\\1`, 'm'))
  return m?.[2]
}

/** Read a module-level truthy boolean flag (`BLANK = True`). */
function pyFlag(source: string, name: string): boolean {
  return new RegExp(`^${name}\\s*=\\s*True\\b`, 'm').test(source)
}

// Host → brand icon. Written as literal icon names so the build-time
// NuxtIconBundle scanner (see vite.config.ts) actually bundles them — there is no
// runtime Iconify fetch, so an icon name that never appears as a literal here
// would render blank. The `simple-icons` collection's prefix contains a hyphen,
// so it MUST use the `prefix:name` colon form: Nuxt UI's Icon strips a leading
// `i-` and hands the rest to Iconify, whose dash parser would otherwise split
// `simple-icons-printables` into prefix `simple` / name `icons-printables` and
// render blank. Colon-form parses unambiguously. Unknown hosts fall back to a
// generic lucide link icon (single-word prefix, dash-form is fine). All slugs
// verified to exist in @iconify-json/simple-icons.
const ICON_BY_HOST: Record<string, string> = {
  'printables.com': 'simple-icons:printables',
  'thingiverse.com': 'simple-icons:thingiverse',
  'etsy.com': 'simple-icons:etsy',
  'youtube.com': 'simple-icons:youtube',
  'github.com': 'simple-icons:github',
  'patreon.com': 'simple-icons:patreon',
  'gumroad.com': 'simple-icons:gumroad',
  'ko-fi.com': 'simple-icons:kofi',
  'instagram.com': 'simple-icons:instagram',
  'discord.com': 'simple-icons:discord',
  'discord.gg': 'simple-icons:discord',
}
const FALLBACK_ICON = 'i-lucide-external-link'

/** Pick a brand icon for a link URL by its host (leading `www.` stripped). */
function iconForUrl(url: string): string {
  let host: string
  try {
    host = new URL(url).hostname.replace(/^www\./, '')
  }
  catch {
    return FALLBACK_ICON
  }
  // Suffix match so `shop.printables.com` still resolves to printables.
  for (const [domain, icon] of Object.entries(ICON_BY_HOST)) {
    if (host === domain || host.endsWith(`.${domain}`))
      return icon
  }
  return FALLBACK_ICON
}

/**
 * Scrape the module-level `LINKS` list of `{"label": ..., "url": ...}` dicts.
 * Values are flat strings (no nested brackets), so a non-greedy match to the
 * first `]` closes the list; per-link icons are resolved from the URL host.
 */
function pyLinks(source: string): DesignLink[] {
  const block = source.match(/^LINKS\s*=\s*\[([\s\S]*?)\]/m)
  if (!block)
    return []
  const links: DesignLink[] = []
  for (const dict of block[1].matchAll(/\{([^}]*)\}/g)) {
    const fields: Record<string, string> = {}
    for (const kv of dict[1].matchAll(/(['"])(label|url)\1\s*:\s*(['"])([\s\S]*?)\3/g))
      fields[kv[2]] = kv[4]
    if (fields.label && fields.url)
      links.push({ label: fields.label, url: fields.url, icon: iconForUrl(fields.url) })
  }
  return links
}

function toMeta(path: string, source: string): DesignMeta {
  const slug = slugOf(path)
  return {
    slug,
    name: pyString(source, 'NAME') ?? slug,
    author: pyString(source, 'AUTHOR'),
    description: pyString(source, 'DESCRIPTION'),
    source,
    thumb: thumbs[`./${slug}/thumb.png`],
    blank: pyFlag(source, 'BLANK'),
    links: pyLinks(source),
  }
}

/** All designs, real ones first and any blank starter(s) last (gallery order). */
export const designs: DesignMeta[] = Object.entries(sources)
  .map(([path, source]) => toMeta(path, source))
  .sort((a, b) => Number(a.blank) - Number(b.blank) || a.slug.localeCompare(b.slug))

const bySlug = new Map(designs.map(d => [d.slug, d]))

export function getDesign(slug: string): DesignMeta | undefined {
  return bySlug.get(slug)
}
