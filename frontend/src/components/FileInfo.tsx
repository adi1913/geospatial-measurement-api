import type { FileInfo as FileInfoData } from "../types/api";
import { formatDateTime } from "../utils/format";

interface FileInfoProps {
  file: FileInfoData;
}

export function FileInfo({ file }: FileInfoProps) {
  const details: [string, string][] = [
    ["Filename", file.filename],
    ["File ID", file.id],
    ["Feature count", String(file.feature_count)],
    ["Source CRS", file.crs ?? "—"],
    ["Uploaded", formatDateTime(file.created_at)],
    ["Last updated", formatDateTime(file.updated_at)],
  ];

  return (
    <section className="card" aria-labelledby="file-heading">
      <div className="card__header">
        <h2 id="file-heading" className="card__title">
          File information
        </h2>
        <span className={`badge badge--${file.status.toLowerCase()}`}>{file.status}</span>
      </div>
      <dl className="details">
        {details.map(([label, value]) => (
          <div key={label} className="details__row">
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
