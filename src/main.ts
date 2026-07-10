import ui from '@nuxt/ui/vue-plugin'
import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'

import App from './App.vue'
import './assets/css/main.css'
import 'virtual:nuxt-icon-bundle/register'

// The app chrome is intentionally light-only (white control panel, light-grey
// viewer). Nuxt UI's Vue plugin drives color mode through VueUse `useDark()`,
// which otherwise follows the OS setting and, on a dark-mode OS, renders the
// form controls dark over our white panels (unreadable labels, navy inputs).
// Pin the scheme to light before the plugin's install() reads it below.
localStorage.setItem('vueuse-color-scheme', 'light')

// Real HTML5-history routing (no hash): `/` is the gallery, `/m/:slug` a design's
// generator. Views are lazy so the gallery landing stays light. BASE_URL carries
// the GitHub Pages project subpath in production. Deep-link refresh is handled by
// the 404.html SPA fallback (see vite.config.ts).
const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', name: 'gallery', component: () => import('./views/Gallery.vue') },
    {
      path: '/m/:slug',
      name: 'generator',
      component: () => import('./views/Generator.vue'),
      props: true,
    },
    // Unknown paths fall back to the gallery.
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

createApp(App).use(router).use(ui).mount('#app')
