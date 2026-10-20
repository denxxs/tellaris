"use client";

import { useEffect, useRef, useState } from "react";
import { Button, Input, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import { cx } from "@/lib/format";
import type { ChatMessage } from "@/lib/types";
import { Avatar } from "./Avatar";

const STARTERS = ["What would make you say yes?", "What do you use today instead?", "What would you pay for it?", "What did people around you say?"];

/** A conversation with one simulated person. They remember how they answered and what they read. */
export function PersonaChat({ runId, pid, name, initial, fill }: { runId: string; pid: string; name: string; initial: ChatMessage[]; fill?: boolean }) {
  const [chat, setChat] = useState<ChatMessage[]>(initial);
  const [msg, setMsg] = useState("");
  const [sending, setSending] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const end = useRef<HTMLDivElement>(null);
  const first = name.split(" ")[0] || "them";

  useEffect(() => setChat(initial), [initial]);
  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [chat.length, sending]);

  const send = async (text: string) => {
    const t = text.trim();
    if (!t || sending) return;
    setSending(true);
    setErr(null);
    setChat((c) => [...c, { role: "user", content: t }]);
    setMsg("");
    try {
      const r = await api.chat(runId, pid, t);
      setChat(r.chat);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setSending(false);
    }
  };

  return (
    <div className={cx("flex flex-col", fill && "h-full min-h-0")}>
      <div className={cx("scroll-thin flex flex-col gap-2.5", fill && "min-h-0 flex-1 overflow-y-auto pr-1")}>
        {chat.length === 0 && (
          <div>
            <p className="mb-2 text-[13px] text-muted">Ask {first} anything. They answer in character and remember what they said.</p>
            <div className="flex flex-wrap gap-1.5">
              {STARTERS.map((s) => (
                <button key={s} onClick={() => send(s)} className="h-7 rounded-md border border-control px-2.5 text-[13px] text-muted hover:bg-active hover:text-text">
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {chat.map((m, i) =>
          m.role === "user" ? (
            <div key={i} className="max-w-[88%] self-end rounded-lg bg-primary px-3 py-2 text-[14px] leading-5 text-primary-ink">
              {m.content}
            </div>
          ) : (
            <div key={i} className="flex max-w-[92%] items-start gap-2 self-start">
              <Avatar seed={pid} size={24} className="mt-0.5" />
              <div className="rounded-lg bg-raised px-3 py-2 text-[14px] leading-5 text-text">{m.content}</div>
            </div>
          ),
        )}
        {sending && (
          <div className="flex items-center gap-2 self-start text-muted">
            <Avatar seed={pid} size={24} />
            <Spinner className="size-4" />
          </div>
        )}
        <div ref={end} />
      </div>
      {err && <p className="mt-2 text-[13px] text-negative">{err}</p>}
      <form
        className="mt-3 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          send(msg);
        }}
      >
        <Input value={msg} onChange={(e) => setMsg(e.target.value)} placeholder={`Ask ${first} anything`} aria-label={`Message ${first}`} />
        <Button type="submit" variant="primary" disabled={!msg.trim() || sending}>
          Send
        </Button>
      </form>
    </div>
  );
}
