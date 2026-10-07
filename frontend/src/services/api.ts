import { API_BASE_URL, MAX_UPLOAD_MB } from "../config";
import type { ApiErrorBody, FileInfo, MeasurementsResponse } from "../types/api";

/** An error that is already phrased for end users. Never carries stack traces. */
export class ApiError extends Error {
  readonly title: string;
  readonly code: string;

  constructor(title: string, message: string, code: string) {
    super(message);
    this.name = "ApiError";
    this.title = title;
    this.code = code;
  }
}

const GENERIC_SERVER_ERROR = new ApiError(
  "Server error",
  "Something went wrong on the server. Please try again in a moment.",
  "INTERNAL_ERROR",
);

/** Turns a backend error code into friendly wording (the backend message is safe to show). */
function friendlyError(code: string, status: number, backendMessage?: string): ApiError {
  switch (code) {
    case "UNSUPPORTED_FILE_TYPE":
      return new ApiError(
        "Unsupported file type",
        "Please upload a .kml file or a .zip archive containing a Shapefile.",
        code,
      );
    case "EMPTY_FILE":
      return new ApiError("Empty file", "The selected file is empty.", code);
    case "FILE_TOO_LARGE":
      return new ApiError("File too large", `The file exceeds the ${MAX_UPLOAD_MB} MB limit.`, code);
    case "INVALID_FILE_CONTENT":
      return new ApiError(
        "Invalid or corrupt file",
        backendMessage ?? "The file content is not valid.",
        code,
      );
    case "INVALID_ARCHIVE":
      return new ApiError(
        "Invalid ZIP archive",
        backendMessage ?? "The ZIP archive could not be used.",
        code,
      );
    case "VALIDATION_ERROR":
      return new ApiError(
        "Invalid request",
        "The upload request was not valid. Please choose a file and try again.",
        code,
      );
    case "FILE_NOT_FOUND":
      return new ApiError("File not found", "This file no longer exists on the server.", code);
    case "MEASUREMENTS_UNAVAILABLE":
    case "FILE_NOT_READY":
      return new ApiError(
        "Measurements unavailable",
        backendMessage ?? "Measurements are not available for this file.",
        code,
      );
    default:
      return status >= 500
        ? GENERIC_SERVER_ERROR
        : new ApiError("Request failed", backendMessage ?? "The request could not be completed.", code);
  }
}

async function errorFromResponse(response: Response): Promise<ApiError> {
  let body: ApiErrorBody | undefined;
  try {
    body = (await response.json()) as ApiErrorBody;
  } catch {
    body = undefined; // e.g. an HTML error page from a proxy
  }
  if (!body?.error?.code) {
    return response.status >= 500
      ? GENERIC_SERVER_ERROR
      : new ApiError("Request failed", "The server returned an unexpected response.", "UNKNOWN");
  }
  return friendlyError(body.error.code, response.status, body.error.message);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, init);
  } catch {
    throw new ApiError(
      "Cannot reach the server",
      "Check that the backend is running and that the API address is correct, then try again.",
      "NETWORK_ERROR",
    );
  }
  if (!response.ok) {
    throw await errorFromResponse(response);
  }
  return (await response.json()) as T;
}

export function uploadFile(file: File): Promise<FileInfo> {
  const form = new FormData();
  form.append("file", file);
  return request<FileInfo>("/api/files/", { method: "POST", body: form });
}

export function getMeasurements(fileId: string): Promise<MeasurementsResponse> {
  return request<MeasurementsResponse>(`/api/files/${encodeURIComponent(fileId)}/measurements/`);
}

/**
 * The backend accepts a valid upload (HTTP 201) even when its content cannot be processed,
 * and reports that with status FAILED. This converts such a result into an ApiError.
 */
export function processingFailure(file: FileInfo): ApiError {
  const message = file.error_message ?? "The file could not be processed.";
  const isMissingCrs = message.toLowerCase().includes("coordinate reference system");
  return new ApiError(
    isMissingCrs ? "Missing coordinate reference system (CRS)" : "File could not be processed",
    message,
    "PROCESSING_FAILED",
  );
}
