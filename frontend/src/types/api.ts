/** Shapes of the JSON returned by the FastAPI backend. */

export type FileStatus = "PROCESSING" | "COMPLETED" | "FAILED";

export type FeatureStatus =
  | "MEASURED"
  | "NOT_APPLICABLE"
  | "UNSUPPORTED"
  | "INVALID"
  | "SKIPPED";

export interface FileInfo {
  id: string;
  filename: string;
  feature_count: number;
  crs: string | null;
  status: FileStatus;
  created_at: string;
  updated_at: string;
  /** Only present when status is FAILED. */
  error_message?: string;
}

export interface Measurement {
  feature_id: number;
  geometry_type: string | null;
  /** Square metres (polygons). */
  area: number | null;
  /** Metres (lines). */
  length: number | null;
  unit: string | null;
  calculation_crs: string | null;
  status: FeatureStatus;
  note: string | null;
}

export interface MeasurementsResponse {
  file_id: string;
  crs: string | null;
  measurements: Measurement[];
}

export interface ApiErrorBody {
  error?: {
    code?: string;
    message?: string;
  };
}
