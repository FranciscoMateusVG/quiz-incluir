/**
 * Media URL resolution, ported from `app/frontend/services/media.py`.
 *
 * This is real logic, not glue — keep the behaviour identical:
 *  1. trim surrounding whitespace;
 *  2. unwrap an `imgurl=` wrapper parameter (some image-search results embed
 *     the actual image URL in a query param, and the <img> needs the direct
 *     one);
 *  3. pass absolute http(s) URLs through untouched;
 *  4. otherwise treat it as relative and join it onto the API base.
 */

const API_BASE = (
  (import.meta.env.VITE_API_URL as string | undefined) ?? ""
).replace(/\/$/, "");

export function resolveMediaUrl(
  url: string | null | undefined,
  baseUrl = API_BASE,
): string {
  if (!url) return "";
  let value = url.trim();

  if (/[?&]imgurl=/.test(value)) {
    try {
      // A relative base keeps URL() happy for protocol-relative/odd inputs.
      const direct = new URL(
        value,
        "http://placeholder.invalid",
      ).searchParams.get("imgurl");
      if (direct) value = direct;
    } catch {
      /* unparseable; fall through with the original value */
    }
  }

  if (/^https?:\/\//i.test(value)) return value;

  return `${baseUrl.replace(/\/$/, "")}/${value.replace(/^\//, "")}`;
}
