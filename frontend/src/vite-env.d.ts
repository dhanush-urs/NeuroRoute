/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL: string
  readonly VITE_WS_URL: string
  readonly VITE_MAP_STYLE_URL: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

interface Window {
  __WS_DEBUG__?: {
    connectedChannels: Record<string, boolean>
  }
}