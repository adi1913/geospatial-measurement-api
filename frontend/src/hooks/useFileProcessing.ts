import { useCallback, useRef, useState } from "react";

import { ApiError, getMeasurements, processingFailure, uploadFile } from "../services/api";
import type { FileInfo, MeasurementsResponse } from "../types/api";

export type ProcessingState =
  | { phase: "idle" }
  | { phase: "uploading" }
  | { phase: "success"; file: FileInfo; measurements: MeasurementsResponse }
  | { phase: "error"; error: ApiError };

const UNEXPECTED_ERROR = new ApiError(
  "Unexpected error",
  "Something unexpected happened. Please try again.",
  "UNEXPECTED",
);

/** Owns the upload -> measurements flow so components only render state. */
export function useFileProcessing() {
  const [state, setState] = useState<ProcessingState>({ phase: "idle" });
  const latestRun = useRef(0);

  const submit = useCallback(async (file: File) => {
    const run = ++latestRun.current;
    setState({ phase: "uploading" });
    try {
      const uploaded = await uploadFile(file);
      if (uploaded.status !== "COMPLETED") {
        throw processingFailure(uploaded);
      }
      const measurements = await getMeasurements(uploaded.id);
      if (run === latestRun.current) {
        setState({ phase: "success", file: uploaded, measurements });
      }
    } catch (error) {
      if (run === latestRun.current) {
        setState({
          phase: "error",
          error: error instanceof ApiError ? error : UNEXPECTED_ERROR,
        });
      }
    }
  }, []);

  const reset = useCallback(() => {
    latestRun.current++; // ignore the result of any request still in flight
    setState({ phase: "idle" });
  }, []);

  return { state, submit, reset };
}
