import { FileInfo } from "./components/FileInfo";
import { FileUpload } from "./components/FileUpload";
import { Header } from "./components/Header";
import { MeasurementTable } from "./components/MeasurementTable";
import { StatusMessage } from "./components/StatusMessage";
import { useFileProcessing } from "./hooks/useFileProcessing";

export default function App() {
  const { state, submit, reset } = useFileProcessing();

  return (
    <>
      <Header />
      <main className="container main">
        {state.phase === "success" ? (
          <>
            <div className="toolbar">
              <p className="toolbar__text">
                Processed <strong>{state.file.filename}</strong> successfully.
              </p>
              <button type="button" className="button" onClick={reset}>
                Upload another file
              </button>
            </div>
            <FileInfo file={state.file} />
            <MeasurementTable measurements={state.measurements.measurements} />
          </>
        ) : (
          <>
            {state.phase === "uploading" && (
              <StatusMessage variant="loading" title="Processing geospatial file...">
                Uploading, reading features and calculating measurements.
              </StatusMessage>
            )}
            {state.phase === "error" && (
              <StatusMessage variant="error" title={state.error.title}>
                {state.error.message}
              </StatusMessage>
            )}
            <FileUpload isProcessing={state.phase === "uploading"} onUpload={submit} />
            {state.phase === "idle" && (
              <p className="empty">
                Results will appear here after you upload a file. Try the samples in
                <code> backend/sample_data</code>.
              </p>
            )}
          </>
        )}
      </main>
      <footer className="footer container">
        Areas and lengths are calculated in a projected metric CRS (UTM), never in degrees.
      </footer>
    </>
  );
}
