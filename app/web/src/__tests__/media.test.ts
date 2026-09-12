import { describe, expect, it } from "vitest";

import { resolveMediaUrl } from "@/lib/media";

describe("resolveMediaUrl", () => {
  it("passes absolute http(s) URLs through untouched", () => {
    expect(resolveMediaUrl("https://picsum.photos/600/400")).toBe(
      "https://picsum.photos/600/400",
    );
    expect(resolveMediaUrl("http://example.com/a.mp3")).toBe(
      "http://example.com/a.mp3",
    );
  });

  it("trims surrounding whitespace", () => {
    expect(resolveMediaUrl("  https://example.com/a.png  ")).toBe(
      "https://example.com/a.png",
    );
  });

  it("unwraps an imgurl wrapper parameter", () => {
    const wrapped =
      "https://wrapper.example/view?imgurl=https%3A%2F%2Fcdn.example%2Freal.jpg&w=800";
    expect(resolveMediaUrl(wrapped)).toBe("https://cdn.example/real.jpg");
  });

  it("unwraps imgurl when it is the first query parameter", () => {
    const wrapped =
      "https://wrapper.example/view?imgurl=https%3A%2F%2Fcdn.example%2Fx.png";
    expect(resolveMediaUrl(wrapped)).toBe("https://cdn.example/x.png");
  });

  it("joins a relative URL onto the API base", () => {
    expect(resolveMediaUrl("media/clip.mp3", "http://localhost:8000")).toBe(
      "http://localhost:8000/media/clip.mp3",
    );
  });

  it("does not double up slashes", () => {
    expect(resolveMediaUrl("/media/clip.mp3", "http://localhost:8000/")).toBe(
      "http://localhost:8000/media/clip.mp3",
    );
  });

  it("returns an empty string for empty input", () => {
    expect(resolveMediaUrl(null)).toBe("");
    expect(resolveMediaUrl(undefined)).toBe("");
    expect(resolveMediaUrl("")).toBe("");
  });
});
