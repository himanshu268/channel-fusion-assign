/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Absolute API origin (https in prod). Empty → same-origin "/api/v1". */
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
