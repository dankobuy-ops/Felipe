import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Container } from "@/components/ui/container";

export default function NotFound() {
  return (
    <section className="py-28">
      <Container className="mx-auto max-w-xl text-center">
        <p className="text-sm font-medium uppercase tracking-wider text-muted-foreground">
          Error 404
        </p>
        <h1 className="mt-3 font-display text-4xl text-foreground sm:text-5xl">
          Página no encontrada
        </h1>
        <p className="mt-4 text-muted-foreground">
          La ruta que buscas no existe o fue movida. Puedes volver al inicio o
          contactarnos si necesitas ayuda.
        </p>
        <div className="mt-8 flex flex-wrap justify-center gap-3">
          <Button asChild>
            <Link href="/">Volver al inicio</Link>
          </Button>
          <Button asChild variant="outline">
            <Link href="/contacto">Contactar</Link>
          </Button>
        </div>
      </Container>
    </section>
  );
}
