import { ALLOWED_EXTENSIONS, MAX_UPLOAD_BYTES, MAX_UPLOAD_MB } from "../config";

/** Returns a user-facing problem description, or null when the file looks acceptable. */
export function validateFile(file: File): string | null {
  const name = file.name.toLowerCase();
  if (!ALLOWED_EXTENSIONS.some((extension) => name.endsWith(extension))) {
    return "Unsupported file type. Please choose a .kml file or a .zip containing a Shapefile.";
  }
  if (file.size === 0) {
    return "This file is empty.";
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    return `This file is larger than the ${MAX_UPLOAD_MB} MB limit.`;
  }
  return null;
}
