import ui from '@nuxt/ui/vue-plugin'
import { createApp } from 'vue'
import { createRouter, createWebHashHistory } from 'vue-router'

import App from './App.vue'
import './assets/css/main.css'
import 'virtual:nuxt-icon-bundle/register'

// The app chrome is intentionally light-only (white control panel, light-grey
// viewer). Nuxt UI's Vue plugin drives color mode through VueUse `useDark()`,
// which otherwise follows the OS setting and, on a dark-mode OS, renders the
// form controls dark over our white panels (unreadable labels, navy inputs).
// Pin the scheme to light before the plugin's install() reads it below.
localStorage.setItem('vueuse-color-scheme', 'light')

// A minimal router exists solely because Nuxt UI's standalone Vue build resolves
// `useRoute`/`useRouter` from vue-router. This is a single-view app, so there are
// no real routes and no <RouterView> — App.vue renders directly.
const router = createRouter({
  history: createWebHashHistory(),
  routes: [{ path: '/', component: App }],
})

createApp(App).use(router).use(ui).mount('#app')
