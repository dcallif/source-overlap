import { computed, ref } from 'vue'

const STORAGE_KEY = 'theme'
const THEME_COLORS = { light: '#e8ebe4', dark: '#111512' }
const darkQuery =
  typeof window !== 'undefined'
    ? window.matchMedia('(prefers-color-scheme: dark)')
    : null

function storedTheme() {
  try {
    const value = localStorage.getItem(STORAGE_KEY)
    return value === 'light' || value === 'dark' ? value : null
  } catch {
    return null
  }
}

function preferredTheme() {
  return storedTheme() || (darkQuery?.matches ? 'dark' : 'light')
}

const theme = ref(
  document.documentElement.dataset.theme || preferredTheme()
)

function applyTheme(value) {
  document.documentElement.dataset.theme = value
  document.documentElement.style.colorScheme = value

  const meta = document.querySelector('meta[name="theme-color"]')
  if (meta) meta.setAttribute('content', THEME_COLORS[value])
}

function setTheme(value) {
  theme.value = value
  applyTheme(value)
  try {
    localStorage.setItem(STORAGE_KEY, value)
  } catch {
    /* Storage can be unavailable in private browsing. */
  }
}

function toggleTheme() {
  setTheme(theme.value === 'dark' ? 'light' : 'dark')
}

darkQuery?.addEventListener?.('change', (event) => {
  if (storedTheme()) return
  theme.value = event.matches ? 'dark' : 'light'
  applyTheme(theme.value)
})

export function useTheme() {
  return {
    theme,
    isDark: computed(() => theme.value === 'dark'),
    toggleTheme,
  }
}
