/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** The published user guide address. The footer link is hidden while empty. */
  readonly VITE_USER_GUIDE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
