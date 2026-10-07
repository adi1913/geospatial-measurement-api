import { useRef, useState } from "react";
import type { ChangeEvent, DragEvent, KeyboardEvent } from "react";

import { ALLOWED_EXTENSIONS, MAX_UPLOAD_MB } from "../config";
import { formatBytes } from "../utils/format";
import { validateFile } from "../utils/file";

interface FileUploadProps {
  isProcessing: boolean;
  onUpload: (file: File) => void;
}

export function FileUpload({ isProcessing, onUpload }: FileUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);

  const canUpload = selectedFile !== null && validationError === null && !isProcessing;

  function selectFile(file: File | undefined) {
    if (!file) return;
    setSelectedFile(file);
    setValidationError(validateFile(file));
  }

  function openPicker() {
    if (!isProcessing) inputRef.current?.click();
  }

  function handleInputChange(event: ChangeEvent<HTMLInputElement>) {
    selectFile(event.target.files?.[0]);
    event.target.value = ""; // allows choosing the same file again
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setIsDragging(false);
    if (!isProcessing) selectFile(event.dataTransfer.files[0]);
  }

  function handleDropzoneKey(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      openPicker();
    }
  }

  return (
    <section className="card" aria-labelledby="upload-heading">
      <h2 id="upload-heading" className="card__title">
        1. Upload a file
      </h2>

      <div
        className={`dropzone${isDragging ? " dropzone--active" : ""}${isProcessing ? " dropzone--disabled" : ""}`}
        role="button"
        tabIndex={isProcessing ? -1 : 0}
        aria-disabled={isProcessing}
        onClick={openPicker}
        onKeyDown={handleDropzoneKey}
        onDragOver={(event) => {
          event.preventDefault();
          if (!isProcessing) setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
      >
        <p className="dropzone__main">Drag &amp; drop a file here, or click to browse</p>
        <p className="dropzone__hint">
          Supported: <strong>.kml</strong> or <strong>.zip</strong> (containing one Shapefile with
          .shp, .shx and .dbf) · Max {MAX_UPLOAD_MB} MB
        </p>
        <input
          ref={inputRef}
          type="file"
          accept={ALLOWED_EXTENSIONS.join(",")}
          onChange={handleInputChange}
          hidden
        />
      </div>

      {selectedFile && (
        <div className="selected-file">
          <div className="selected-file__details">
            <span className="selected-file__name">{selectedFile.name}</span>
            <span className="selected-file__size">{formatBytes(selectedFile.size)}</span>
          </div>
          {validationError && (
            <p className="field-error" role="alert">
              {validationError}
            </p>
          )}
        </div>
      )}

      <button
        type="button"
        className="button button--primary"
        disabled={!canUpload}
        onClick={() => selectedFile && onUpload(selectedFile)}
      >
        {isProcessing ? "Processing…" : "Upload and measure"}
      </button>
    </section>
  );
}
