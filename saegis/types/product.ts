import type { LucideIcon } from "lucide-react";

export type Audience = "personas" | "empresas" | "comunidades";

export interface Coverage {
  title: string;
  description: string;
  optional?: boolean;
  highlighted?: boolean;
}

export interface Product {
  slug: string;
  title: string;
  shortDescription: string;
  longDescription: string;
  coverages: Coverage[];
  icon: LucideIcon;
  audience: Audience;
  featured?: boolean;
  tag?: string;
}

export interface Partner {
  name: string;
  slug: string;
  ext: string;
  width: number;
  height: number;
}

export interface Testimonial {
  quote: string;
  name: string;
  role: string;
}
