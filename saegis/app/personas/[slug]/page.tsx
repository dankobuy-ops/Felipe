import { notFound } from "next/navigation";
import { ProductDetail } from "@/components/marketing/ProductDetail";
import { CTA } from "@/components/marketing/CTA";
import { PartnersStrip } from "@/components/marketing/PartnersStrip";
import { products, productsBySlug } from "@/content/products";
import { buildMetadata } from "@/lib/seo";
import { breadcrumbSchema } from "@/lib/structured-data";

interface PageProps {
  params: Promise<{ slug: string }>;
}

export function generateStaticParams() {
  return products.map((p) => ({ slug: p.slug }));
}

export async function generateMetadata({ params }: PageProps) {
  const { slug } = await params;
  const product = productsBySlug.get(slug);
  if (!product) return buildMetadata({ title: "No encontrado", noindex: true });
  return buildMetadata({
    title: product.title,
    description: product.shortDescription,
    path: `/personas/${product.slug}`,
  });
}

export default async function PersonaProductPage({ params }: PageProps) {
  const { slug } = await params;
  const product = productsBySlug.get(slug);
  if (!product) notFound();

  const breadcrumbs = breadcrumbSchema([
    { name: "Inicio", url: "/" },
    { name: "Personas", url: "/personas" },
    { name: product.title, url: `/personas/${product.slug}` },
  ]);

  return (
    <>
      <ProductDetail product={product} />
      <PartnersStrip />
      <CTA
        title={`Cotiza tu ${product.title.toLowerCase()} hoy`}
        description="Un asesor revisa tu caso y te envía alternativas con las principales aseguradoras del país."
      />
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(breadcrumbs) }}
      />
    </>
  );
}
