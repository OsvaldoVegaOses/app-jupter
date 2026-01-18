interface ManifestSummaryProps {
  manifest: Record<string, any> | null | undefined;
}

export function ManifestSummary({ manifest }: ManifestSummaryProps) {
  if (!manifest) {
    return (
      <section className="manifest">
        <h2>Manifesto del informe</h2>
        <p>No se encuentra report_manifest.json. Ejecuta `python main.py report build` para generarlo.</p>
      </section>
    );
  }

  const report = manifest.report || {};
  const snapshot = manifest.snapshot || {};
  const saturation = manifest.saturation || {};

  return (
    <section className="manifest">
      <h2>Manifesto del informe</h2>
      <dl>
        <div>
          <dt>Generado</dt>
          <dd>{manifest.generated_at || "-"}</dd>
        </div>
        <div>
          <dt>Archivo</dt>
          <dd>{report.path || "-"}</dd>
        </div>
        <div>
          <dt>Hash</dt>
          <dd>{report.hash || "-"}</dd>
        </div>
        <div>
          <dt>Fragmentos</dt>
          <dd>{snapshot.fragmentos ?? "-"}</dd>
        </div>
        <div>
          <dt>Codigos</dt>
          <dd>{snapshot.codigos ?? "-"}</dd>
        </div>
        <div>
          <dt>Categorias</dt>
          <dd>{snapshot.categorias ?? "-"}</dd>
        </div>
        <div>
          <dt>Saturacion</dt>
          <dd>{JSON.stringify(saturation)}</dd>
        </div>
      </dl>
    </section>
  );
}
