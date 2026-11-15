// One WebSocket to the adapter, re-opened with a growing wait if it drops.
import { ADAPTER_URL } from "./api";
import type { Answer, ServerEvent } from "./types";

export type SocketStatus = "connecting" | "open" | "closed" | "unauthorized";

const RETRY_MS = [500, 1000, 2000, 5000];

export class SpaceSocket {
  private ws: WebSocket | null = null;
  private attempt = 0;
  private stopped = false;
  private waiting = new Map<string, (a: Answer) => void>();

  constructor(
    private token: string,
    private onEvent: (e: ServerEvent) => void,
    private onStatus: (s: SocketStatus) => void,
  ) {}

  open(): void {
    this.stopped = false;
    const base = ADAPTER_URL || `${location.protocol}//${location.host}`;
    const url = `${base.replace(/^http/, "ws")}/ws`;
    this.onStatus("connecting");
    const ws = new WebSocket(url);
    this.ws = ws;
    ws.onopen = () => ws.send(JSON.stringify({ type: "auth", token: this.token }));
    ws.onmessage = (msg) => {
      const event = JSON.parse(msg.data) as ServerEvent;
      if (event.type === "hello") {
        this.attempt = 0;
        this.onStatus("open");
      }
      if (event.type === "reply") {
        this.waiting.get(event.requestId)?.(event.answer);
        this.waiting.delete(event.requestId);
        return;
      }
      this.onEvent(event);
    };
    ws.onclose = (e) => {
      if (e.code === 4401) {
        this.onStatus("unauthorized");
        return;
      }
      this.onStatus("closed");
      if (!this.stopped) setTimeout(() => this.open(), RETRY_MS[Math.min(this.attempt++, RETRY_MS.length - 1)]);
    };
  }

  close(): void {
    this.stopped = true;
    this.ws?.close();
  }

  say(text: string): void {
    this.ws?.send(JSON.stringify({ type: "message", text }));
  }

  ask(frame: { type: "command"; command: "profile" | "kickoff" | "state"; args?: object } | { type: "click"; proposalId: string; action: "confirm" | "reject" }): Promise<Answer> {
    const requestId = crypto.randomUUID();
    return new Promise((resolve) => {
      this.waiting.set(requestId, resolve);
      this.ws?.send(JSON.stringify({ ...frame, requestId }));
    });
  }
}
