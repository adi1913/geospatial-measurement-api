/** The only place that reads environment variables. */

const DEFAULT_API_BASE_URL = "http://localhost:8000";
const DEFAULT_MAX_UPLOAD_MB = 20;

export const API_BASE_URL: string = (
  import.meta.env.VITE_API_BASE_URL || DEFAULT_API_BASE_URL
).replace(/\/+$/, "");

const configuredMax = Number(import.meta.env.VITE_MAX_UPLOAD_MB);
export const MAX_UPLOAD_MB: number =
  Number.isFinite(configuredMax) && configuredMax > 0 ? configuredMax : DEFAULT_MAX_UPLOAD_MB;

export const MAX_UPLOAD_BYTES: number = MAX_UPLOAD_MB * 1024 * 1024;

export const ALLOWED_EXTENSIONS = [".kml", ".zip"] as const;
