import { ExternalLink } from "lucide-react";

export function GoogleFormEmbed({
  url,
  shareUrl,
  title = "Formulario de contacto",
  height = 900,
}: {
  url: string;
  shareUrl?: string;
  title?: string;
  height?: number;
}) {
  const isPlaceholder = url.includes("PLACEHOLDER");
  return (
    <div
      id="formulario"
      className="overflow-hidden rounded-2xl border border-border bg-background shadow-[var(--shadow-card)]"
    >
      {isPlaceholder ? (
        <div className="flex flex-col items-start gap-3 p-8 text-sm">
          <p className="font-medium text-foreground">
            Formulario pendiente de configuración.
          </p>
          <p className="text-muted-foreground">
            Reemplaza{" "}
            <code className="rounded bg-muted px-1 py-0.5 text-xs">googleFormUrl</code>{" "}
            en <code className="rounded bg-muted px-1 py-0.5 text-xs">content/company.ts</code>{" "}
            con la URL real de tu formulario de Google.
          </p>
        </div>
      ) : (
        <iframe
          src={url}
          title={title}
          width="100%"
          height={height}
          frameBorder={0}
          loading="lazy"
          className="block w-full"
        >
          Cargando formulario…
        </iframe>
      )}
      {shareUrl && !isPlaceholder && (
        <div className="flex items-center justify-end border-t border-border bg-surface px-4 py-3">
          <a
            href={shareUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-xs font-medium text-primary hover:underline"
          >
            Abrir formulario en una pestaña nueva
            <ExternalLink className="size-3" />
          </a>
        </div>
      )}
    </div>
  );
}
