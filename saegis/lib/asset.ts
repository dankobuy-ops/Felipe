const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

/** Prefix a public asset path with basePath so it works both on
 *  GitHub Pages (/website/...) and on the final custom domain (/...). */
export function asset(path: string): string {
  if (!path.startsWith("/")) return path;
  return `${basePath}${path}`;
}
