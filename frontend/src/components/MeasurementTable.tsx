import type { FeatureStatus, Measurement } from "../types/api";
import { formatNumber } from "../utils/format";

interface MeasurementTableProps {
  measurements: Measurement[];
}

const STATUS_LABELS: Record<FeatureStatus, string> = {
  MEASURED: "Measured",
  NOT_APPLICABLE: "No measurement",
  UNSUPPORTED: "Unsupported",
  INVALID: "Invalid",
  SKIPPED: "Skipped",
};

function measuredValue(measurement: Measurement): number | null {
  return measurement.area ?? measurement.length;
}

export function MeasurementTable({ measurements }: MeasurementTableProps) {
  const measuredCount = measurements.filter((m) => m.status === "MEASURED").length;

  return (
    <section className="card" aria-labelledby="measurements-heading">
      <div className="card__header">
        <h2 id="measurements-heading" className="card__title">
          Measurements
        </h2>
        <span className="card__meta">
          {measuredCount} of {measurements.length} feature{measurements.length === 1 ? "" : "s"}{" "}
          measured
        </span>
      </div>

      {measurements.length === 0 ? (
        <p className="empty">No features were found in this file.</p>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Feature ID</th>
                <th scope="col">Geometry Type</th>
                <th scope="col" className="num">
                  Measurement
                </th>
                <th scope="col">Unit</th>
                <th scope="col">Calculated in</th>
                <th scope="col">Status</th>
              </tr>
            </thead>
            <tbody>
              {measurements.map((measurement) => {
                const value = measuredValue(measurement);
                return (
                  <tr key={measurement.feature_id}>
                    <td>{measurement.feature_id}</td>
                    <td>{measurement.geometry_type ?? "—"}</td>
                    <td className="num">{value === null ? "—" : formatNumber(value)}</td>
                    <td>{value === null ? "—" : (measurement.unit ?? "—")}</td>
                    <td>{measurement.calculation_crs ?? "—"}</td>
                    <td>
                      <span className={`pill pill--${measurement.status.toLowerCase()}`}>
                        {STATUS_LABELS[measurement.status]}
                      </span>
                      {measurement.note && measurement.status !== "NOT_APPLICABLE" && (
                        <span className="note">{measurement.note}</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
