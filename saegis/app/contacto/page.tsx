import { Container } from "@/components/ui/container";
import { ContactInfo } from "@/components/contact/ContactInfo";
import { GoogleFormEmbed } from "@/components/contact/GoogleFormEmbed";
import { PartnersStrip } from "@/components/marketing/PartnersStrip";
import { buildMetadata } from "@/lib/seo";
import { company } from "@/content/company";

export const metadata = buildMetadata({
  title: "Contacto",
  description:
    "Cotiza tu seguro con Seguros Aegis. Teléfono, email y formulario de contacto directo.",
  path: "/contacto",
});

export default function ContactoPage() {
  return (
    <>
      <section className="bg-primary text-primary-foreground">
        <Container className="py-20 md:py-28">
          <div className="max-w-3xl space-y-6">
            <p className="text-sm uppercase tracking-wider text-primary-foreground/60">
              Contacto
            </p>
            <h1 className="font-display text-4xl leading-[1.05] sm:text-5xl md:text-6xl">
              Conversemos sobre{" "}
              <span className="text-accent">tu protección</span>.
            </h1>
            <p className="max-w-2xl text-lg leading-relaxed text-primary-foreground/80">
              Cuéntanos qué necesitas y te respondemos el mismo día hábil. Llámanos, escríbenos por email o envíanos tu consulta por el formulario.
            </p>
          </div>
        </Container>
      </section>

      <section className="section-y">
        <Container className="grid gap-12 lg:grid-cols-[1fr_1.6fr] lg:gap-16">
          <div className="space-y-8">
            <div>
              <p className="mb-3 text-sm font-medium uppercase tracking-wider text-muted-foreground">
                Canales de contacto
              </p>
              <h2 className="font-display text-2xl text-foreground sm:text-3xl">
                Estamos a un clic de distancia.
              </h2>
            </div>
            <ContactInfo />
            <p className="text-xs text-muted-foreground">
              {company.name} está inscrita en el Registro de Corredores de Seguros de la Comisión para el Mercado Financiero (CMF).
            </p>
          </div>
          <div>
            <p className="mb-3 text-sm font-medium uppercase tracking-wider text-muted-foreground">
              Formulario
            </p>
            <h2 className="mb-6 font-display text-2xl text-foreground sm:text-3xl">
              Cuéntanos qué seguro necesitas.
            </h2>
            <GoogleFormEmbed
              url={company.googleFormUrl}
              shareUrl={company.googleFormUrlShare}
            />
          </div>
        </Container>
      </section>

      <PartnersStrip subtitle="Aseguradoras" title="Comparamos propuestas entre 12 aseguradoras líderes" />
    </>
  );
}
