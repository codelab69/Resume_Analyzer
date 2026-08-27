/// <reference types="vite/client" />

/**
 * Typed environment variables.
 *
 * Vite only exposes variables prefixed with VITE_ to client code - anything
 * else stays on the build machine. Declaring them here means a typo in
 * `import.meta.env.VITE_API_UR` is a compile error rather than `undefined`
 * silently becoming the base URL.
 */
interface ImportMetaEnv {
  /**
   * Origin of the backend API, e.g. "https://api.example.com".
   * Left unset in development: vite.config.ts proxies /api instead.
   */
  readonly VITE_API_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
