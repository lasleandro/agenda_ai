"use client";

import { useCallback, useRef, useState } from "react";
import Image from "next/image";
import { AssistantPanel } from "./assistant-panel";

const DRAG_THRESHOLD = 5;
const PANEL_GAP = 12;
const VIEWPORT_MARGIN = 16;

// Every Dialog/Popover/Select/DropdownMenu in this app renders at z-50 —
// the assistant must always sit above any of them, on any screen.
const FLOAT_Z = "z-[70]";

type ButtonRect = { top: number; left: number; width: number; height: number };

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

export function FloatingChat() {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState({ x: 0, y: 0 });
  const [buttonRect, setButtonRect] = useState<ButtonRect | null>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const offset = useRef({ x: 0, y: 0 });
  const start = useRef({ x: 0, y: 0 });
  const size = useRef({ width: 56, height: 56 });

  const onPointerDown = useCallback((e: React.PointerEvent) => {
    start.current = { x: e.clientX, y: e.clientY };
    const rect = buttonRef.current!.getBoundingClientRect();
    offset.current = { x: e.clientX - rect.left, y: e.clientY - rect.top };
    size.current = { width: rect.width, height: rect.height };
    buttonRef.current!.setPointerCapture(e.pointerId);
  }, []);

  const onPointerMove = useCallback(
    (e: React.PointerEvent) => {
      if (!e.currentTarget.hasPointerCapture(e.pointerId)) return;
      const nextPos = {
        x: clamp(
          e.clientX - offset.current.x,
          VIEWPORT_MARGIN,
          window.innerWidth - size.current.width - VIEWPORT_MARGIN
        ),
        y: clamp(
          e.clientY - offset.current.y,
          VIEWPORT_MARGIN,
          window.innerHeight - size.current.height - VIEWPORT_MARGIN
        ),
      };
      setPos(nextPos);
      if (open) {
        // Panel is open — keep it glued to the ball as it's dragged,
        // flipping direction live if it crosses the screen's midpoint.
        setButtonRect({
          top: nextPos.y,
          left: nextPos.x,
          width: size.current.width,
          height: size.current.height,
        });
      }
    },
    [open]
  );

  const onPointerUp = useCallback((e: React.PointerEvent) => {
    const dx = e.clientX - start.current.x;
    const dy = e.clientY - start.current.y;
    if (Math.abs(dx) < DRAG_THRESHOLD && Math.abs(dy) < DRAG_THRESHOLD) {
      setOpen((wasOpen) => {
        if (!wasOpen) {
          // Recompute placement every time it opens, from the button's
          // actual current position (default or dragged) — never a fixed
          // "always opens up-left" offset, so it can't render off-screen.
          const rect = buttonRef.current!.getBoundingClientRect();
          setButtonRect({
            top: rect.top,
            left: rect.left,
            width: rect.width,
            height: rect.height,
          });
        }
        return !wasOpen;
      });
    }
  }, []);

  const isDragged = pos.x !== 0 || pos.y !== 0;
  const buttonStyle: React.CSSProperties = isDragged
    ? { left: pos.x, top: pos.y, right: "auto", bottom: "auto" }
    : {};

  let panelStyle: React.CSSProperties | undefined;
  if (buttonRect) {
    const panelWidth = Math.min(384, window.innerWidth - VIEWPORT_MARGIN * 2);
    const panelHeight = Math.min(600, window.innerHeight - VIEWPORT_MARGIN * 2);
    const openUpward = buttonRect.top > window.innerHeight / 2;
    const desiredTop = openUpward
      ? buttonRect.top - panelHeight - PANEL_GAP
      : buttonRect.top + buttonRect.height + PANEL_GAP;
    const desiredLeft = buttonRect.left > window.innerWidth / 2
      ? buttonRect.left + buttonRect.width - panelWidth
      : buttonRect.left;
    panelStyle = {
      top: clamp(
        desiredTop,
        VIEWPORT_MARGIN,
        window.innerHeight - panelHeight - VIEWPORT_MARGIN
      ),
      left: clamp(
        desiredLeft,
        VIEWPORT_MARGIN,
        window.innerWidth - panelWidth - VIEWPORT_MARGIN
      ),
    };
  }

  return (
    <>
      <button
        ref={buttonRef}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        className={`floating-chat-launcher fixed ${FLOAT_Z} flex h-14 w-14 items-center justify-center rounded-full shadow-lg transition-transform hover:scale-110 cursor-grab active:cursor-grabbing touch-none select-none`}
        style={buttonStyle}
        title="Assistente"
      >
        <Image
          src="/tennis.png"
          alt="Assistente"
          width={56}
          height={56}
          className="rounded-full pointer-events-none"
        />
      </button>

      <div
        hidden={!open}
        className={`fixed ${FLOAT_Z} flex h-[min(600px,calc(100dvh-2rem))] w-[calc(100vw-2rem)] max-w-96 flex-col overflow-hidden rounded-lg border bg-background shadow-2xl`}
        style={panelStyle}
      >
        <AssistantPanel onClose={() => setOpen(false)} />
      </div>
    </>
  );
}
