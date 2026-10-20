"use client";

import * as notionists from "@dicebear/notionists";
import { createAvatar } from "@dicebear/core";
import { memo, useMemo } from "react";
import { cx } from "@/lib/format";

// Pale identity tints, far enough apart that neighbours read as different people.
const TINTS = ["dff0f3", "f4ead6", "e5e9f7", "e9f1e1", "f6e3e6", "ece5f3", "f0ece2", "e2eef0"];

function hash(s: string) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

/** An illustrated face for a simulated person, drawn locally from their id (DiceBear "Notionists", CC0). */
function AvatarInner({ seed, size = 32, className, ring }: { seed: string; size?: number; className?: string; ring?: string }) {
  const uri = useMemo(
    () =>
      createAvatar(notionists, {
        seed,
        size: 96,
        backgroundColor: [TINTS[hash(seed) % TINTS.length]],
      }).toDataUri(),
    [seed],
  );
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={uri}
      alt=""
      width={size}
      height={size}
      className={cx("shrink-0 rounded-full", className)}
      style={ring ? { boxShadow: `0 0 0 2px var(--surface), 0 0 0 3.5px ${ring}` } : undefined}
    />
  );
}

export const Avatar = memo(AvatarInner);
