import { productsBySlug } from "@/content/products";
import { ProductDetail } from "@/components/marketing/ProductDetail";
import { CTA } from "@/components/marketing/CTA";
import { PartnersStrip } from "@/components/marketing/PartnersStrip";
import { buildMetadata } from "@/lib/seo";
import { notFound } from "next/navigation";

const product = productsBySlug.get("vehiculo");

export const metadata = buildMetadata({
  title: "Seguro Vehicular",
  description:
    "Seguro automotriz en Chile con daño material, robo, responsabilidad civil, asistencia en ruta y cobertura Mercosur.",
  path: "/seguros/vehicular",
});

export default function SeguroVehicularPage() {
  if (!product) notFound();
  return (
    <>
      <ProductDetail product={product} />
      <PartnersStrip />
      <CTA
        title="Cotiza tu seguro vehicular hoy"
        description="Te enviamos alternativas de las principales aseguradoras para que compares deducibles, asistencias y precios."
      />
    </>
  );
}
