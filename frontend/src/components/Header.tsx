export function Header() {
  return (
    <header className="header">
      <div className="container header__inner">
        <span className="header__logo" aria-hidden="true">
          <svg viewBox="0 0 32 32" width="28" height="28">
            <path d="M6 23l6-13 5 9 3-5 6 9z" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinejoin="round" />
          </svg>
        </span>
        <div>
          <h1 className="header__title">Geospatial File Measurement</h1>
          <p className="header__subtitle">
            Upload a KML or zipped Shapefile and get the area of every polygon and the length of
            every line, calculated in metres.
          </p>
        </div>
      </div>
    </header>
  );
}
