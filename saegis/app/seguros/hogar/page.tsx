import { productsBySlug } from "@/content/products";
import { ProductDetail } from "@/components/marketing/ProductDetail";
import { CTA } from "@/components/marketing/CTA";
import { PartnersStrip } from "@/components/marketing/PartnersStrip";
import { buildMetadata } from "@/lib/seo";
import { notFound } from "next/navigation";

const product = productsBySlug.get("hogar");

export const metadata = buildMetadata({
  title: "Seguro Hogar",
  description:
    "Seguro integral para tu casa o departamento: incendio, sismo, robo, daño por agua y asistencia 24/7.",
  path: "/seguros/hogar",
});

export default function SeguroHogarPage() {
  if (!product) notFound();
  return (
    <>
      <ProductDetail product={product} />
      <PartnersStrip />
      <CTA
        title="Cotiza tu seguro de hogar"
        description="Protege tu inversión más importante. Un asesor te orienta en minutos."
      />
    </>
  );
}
