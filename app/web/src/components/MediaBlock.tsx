import { useQuery } from "@tanstack/react-query";
import { ExternalLink } from "lucide-react";
import { useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { type MediaRead, type QuizMediaRead } from "@/api/types";
import { t } from "@/i18n/pt-BR";
import { resolveMediaUrl } from "@/lib/media";

type AnyMedia = MediaRead | QuizMediaRead;

/**
 * Renders a question's or quiz's media.
 *
 * This replaces `widgets/media.py`, `services/media.py` and
 * `services/page_store.py` wholesale. All three existed to manage a single
 * per-session Flet `Audio` *service* that had to be registered before the page
 * rendered, and whose module-global instance leaked between browser sessions
 * (audio started by one student played on another's page). In the browser it
 * is an <audio> element.
 */
export function MediaBlock({ media }: { media: AnyMedia[] }) {
  if (media.length === 0) return null;

  const ordered = [...media].sort((a, b) => a.position - b.position);

  return (
    <>
      {ordered.map((item) => (
        <MediaItem key={item.id} media={item} />
      ))}
    </>
  );
}

function MediaItem({ media }: { media: AnyMedia }) {
  const url = media.url ?? "";
  const caption = media.caption ?? "";
  const resolved = url ? resolveMediaUrl(url) : "";

  let body: React.ReactNode = null;
  // Captions accompany the media for every type except text, where the
  // caption *is* the content (media.py:156).
  let showCaption = true;

  switch (media.type) {
    case "image":
      if (resolved) body = <ImageMedia src={resolved} caption={caption} />;
      break;

    case "text":
      if (caption || url) {
        body = <TextMedia url={resolved} caption={caption} />;
        showCaption = false;
      }
      break;

    case "audio":
      if (resolved) {
        body = (
          <audio
            controls
            preload="metadata"
            className="w-full"
            src={resolved}
          />
        );
      }
      break;

    case "video":
      if (resolved) {
        body = (
          <video
            controls
            preload="metadata"
            className="aspect-video w-full rounded-card bg-black"
            src={resolved}
          />
        );
      }
      break;
  }

  // Unknown type but a usable URL: offer to open it, as the Flet fallback did.
  if (!body && resolved) {
    body = (
      <a
        href={resolved}
        target="_blank"
        rel="noreferrer"
        className="inline-flex items-center gap-2 text-sm text-primary hover:underline"
      >
        <ExternalLink className="size-4" />
        {t.openMedia}
      </a>
    );
  }

  if (!body) return null;

  return (
    <div className="space-y-1 rounded-card border border-border bg-background p-2">
      {body}
      {showCaption && caption ? (
        <p className="text-xs text-muted-foreground">{caption}</p>
      ) : null}
    </div>
  );
}

function ImageMedia({ src, caption }: { src: string; caption: string }) {
  const [failed, setFailed] = useState(false);

  if (failed) {
    return (
      <p className="italic text-muted-foreground">
        {caption || t.mediaUnavailable}
      </p>
    );
  }

  return (
    <img
      src={src}
      alt={caption}
      className="h-[180px] w-full rounded-card object-contain"
      onError={() => setFailed(true)}
    />
  );
}

/**
 * Markdown content — a reading passage, typically.
 *
 * Every TEXT media row in the seeds carries its passage inline in `caption`
 * and has no `url`, so that is the common path and it needs no network at all.
 * The `url` branch is kept for parity with the Flet widget, which fetched the
 * markdown file server-side. Note it now runs in the browser, so a remote file
 * needs CORS on its host; failure falls back to the caption exactly as before.
 */
function TextMedia({ url, caption }: { url: string; caption: string }) {
  const { data } = useQuery({
    queryKey: ["media-text", url],
    enabled: Boolean(url),
    staleTime: Infinity,
    retry: false,
    queryFn: async () => {
      const resp = await fetch(url);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      return resp.text();
    },
  });

  const content = data ?? caption;
  if (!content) return null;

  return (
    <div className="prose-quiz space-y-2 text-sm leading-relaxed">
      <Markdown remarkPlugins={[remarkGfm]}>{content}</Markdown>
    </div>
  );
}
