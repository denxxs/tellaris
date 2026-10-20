"use client";

import { useRef, useState } from "react";
import { Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import { cx, int } from "@/lib/format";
import type { UploadedFile } from "@/lib/types";

const ACCEPT = ".pdf,.docx,.pptx,.xlsx,.csv,.txt,.md,.markdown,.json,.html,.htm";

function size(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/** Attach pitch decks, product docs, pricing pages or research as context. */
export function FileDrop({ files, onChange }: { files: UploadedFile[]; onChange: (f: UploadedFile[]) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);

  const upload = async (list: FileList | File[]) => {
    const arr = Array.from(list);
    if (!arr.length) return;
    setBusy(true);
    setErrors([]);
    try {
      const r = await api.upload(arr);
      onChange([...files, ...r.files]);
      setErrors(r.errors);
    } catch (e) {
      setErrors([(e as Error).message]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setOver(false);
          upload(e.dataTransfer.files);
        }}
        className={cx("flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md border border-dashed px-3 py-2.5 transition-colors", over ? "border-text bg-raised" : "border-control")}
      >
        {busy ? <Spinner className="size-4 text-muted" /> : (
          <svg viewBox="0 0 24 24" className="size-4 text-muted" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
            <path d="M21 12.5 12.6 21a5 5 0 0 1-7.1-7.1l8.5-8.4a3.3 3.3 0 0 1 4.7 4.7L10.3 18.6a1.7 1.7 0 0 1-2.4-2.4l7.8-7.7" />
          </svg>
        )}
        <span className="text-[14px] text-muted">
          {busy ? "Reading your files…" : "Drop a pitch deck, product doc, pricing page or research here, or"}
        </span>
        {!busy && (
          <button type="button" onClick={() => input.current?.click()} className="text-[14px] font-medium text-text underline-offset-2 hover:underline">
            choose files
          </button>
        )}
        <input
          ref={input}
          type="file"
          multiple
          accept={ACCEPT}
          className="hidden"
          onChange={(e) => {
            if (e.target.files) upload(e.target.files);
            e.target.value = "";
          }}
        />
      </div>
      {files.length > 0 && (
        <ul className="mt-2 flex flex-col">
          {files.map((f) => (
            <li key={f.id} className="flex items-center gap-3 border-b border-rule py-2 last:border-0">
              <span className="grid h-7 w-9 shrink-0 place-items-center rounded bg-raised text-[11px] font-medium uppercase text-muted">{f.name.split(".").pop()}</span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[14px] text-text">{f.name}</span>
                <span className="block text-[12px] text-faint">
                  {size(f.size)}, {int(f.chars)} characters read{f.truncated ? ", long file shortened" : ""}
                </span>
              </span>
              <button
                type="button"
                onClick={() => {
                  onChange(files.filter((x) => x.id !== f.id));
                  api.deleteFile(f.id).catch(() => {});
                }}
                className="rounded px-1.5 py-0.5 text-[13px] text-muted hover:bg-active hover:text-text"
                aria-label={`Remove ${f.name}`}
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
      {errors.map((e) => (
        <p key={e} className="mt-1.5 text-[13px] text-negative">
          {e}
        </p>
      ))}
    </div>
  );
}
