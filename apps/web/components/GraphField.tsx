"use client";

import { useEffect, useRef } from "react";

type Node = {
  x: number;
  y: number;
  r: number;
  phase: number;
  speed: number;
  drift: number;
  color: string;
};

const COLORS = ["#ffffff", "#f6c56b", "#8ee7dc", "#c4b5fd", "#fb923c", "#93c5fd"];

function createNodes(width: number, height: number): Node[] {
  const count = Math.round(Math.min(78, Math.max(42, (width * height) / 18000)));
  const nodes: Node[] = [];
  for (let index = 0; index < count; index += 1) {
    const bias = Math.random();
    nodes.push({
      x: width * (0.28 + bias * 0.78),
      y: height * (0.08 + Math.random() * 0.84),
      r: 1.1 + Math.random() * 2.6,
      phase: Math.random() * Math.PI * 2,
      speed: 0.15 + Math.random() * 0.45,
      drift: 8 + Math.random() * 22,
      color: COLORS[index % COLORS.length] ?? "#ffffff",
    });
  }
  return nodes;
}

function runGraph(field: HTMLCanvasElement, ctx: CanvasRenderingContext2D) {
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  let nodes: Node[] = [];
  let width = 0;
  let height = 0;
  let frame = 0;
  let pointerX = 0;
  let pointerY = 0;
  const pulses = Array.from({ length: 5 }, () => Math.random());

  function resize() {
    const rect = field.getBoundingClientRect();
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    width = rect.width;
    height = rect.height;
    field.width = Math.max(1, Math.floor(width * dpr));
    field.height = Math.max(1, Math.floor(height * dpr));
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    nodes = createNodes(width, height);
  }

  function draw(time: number) {
    if (width < 2 || height < 2) {
      if (!reduced) frame = window.requestAnimationFrame(draw);
      return;
    }
    ctx.clearRect(0, 0, width, height);
    const seconds = time / 1000;
    const positions = nodes.map((node) => {
      const wobbleX = Math.sin(seconds * node.speed + node.phase) * node.drift;
      const wobbleY = Math.cos(seconds * node.speed * 0.8 + node.phase) * node.drift;
      return {
        x: node.x + wobbleX + (pointerX - width / 2) * 0.015,
        y: node.y + wobbleY + (pointerY - height / 2) * 0.015,
        node,
      };
    });

    const linkDistance = Math.min(168, width * 0.16);
    for (let i = 0; i < positions.length; i += 1) {
      for (let j = i + 1; j < positions.length; j += 1) {
        const a = positions[i];
        const b = positions[j];
        if (!a || !b) continue;
        const distance = Math.hypot(a.x - b.x, a.y - b.y);
        if (distance > linkDistance) continue;
        ctx.strokeStyle = `rgba(186, 210, 255, ${(1 - distance / linkDistance) * 0.45})`;
        ctx.lineWidth = 0.7;
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();
      }
    }

    pulses.forEach((seed, index) => {
      const a = positions[index * 7];
      const b = positions[index * 7 + 3];
      if (!a || !b) return;
      const t = (seconds * 0.18 + seed) % 1;
      ctx.fillStyle = "rgba(255,255,255,0.9)";
      ctx.beginPath();
      ctx.arc(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t, 1.6, 0, Math.PI * 2);
      ctx.fill();
    });

    for (const point of positions) {
      const glow = 0.55 + Math.sin(seconds * 1.4 + point.node.phase) * 0.25;
      const gradient = ctx.createRadialGradient(point.x, point.y, 0, point.x, point.y, point.node.r * 8);
      gradient.addColorStop(0, point.node.color);
      gradient.addColorStop(1, "transparent");
      ctx.fillStyle = gradient;
      ctx.globalAlpha = 0.35 * glow;
      ctx.beginPath();
      ctx.arc(point.x, point.y, point.node.r * 8, 0, Math.PI * 2);
      ctx.fill();
      ctx.globalAlpha = 1;
      ctx.fillStyle = point.node.color;
      ctx.beginPath();
      ctx.arc(point.x, point.y, point.node.r, 0, Math.PI * 2);
      ctx.fill();
    }

    if (!reduced) frame = window.requestAnimationFrame(draw);
  }

  function onPointer(event: PointerEvent) {
    const rect = field.getBoundingClientRect();
    pointerX = event.clientX - rect.left;
    pointerY = event.clientY - rect.top;
  }

  resize();
  const observer = new ResizeObserver(() => resize());
  observer.observe(field);
  pointerX = width * 0.72;
  pointerY = height * 0.4;
  window.addEventListener("pointermove", onPointer);
  frame = window.requestAnimationFrame(draw);

  return () => {
    window.cancelAnimationFrame(frame);
    observer.disconnect();
    window.removeEventListener("pointermove", onPointer);
  };
}

export function GraphField({ className = "" }: { className?: string }) {
  const surfaceRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const field = surfaceRef.current;
    const ctx = field?.getContext("2d");
    if (!field || !ctx) return;
    return runGraph(field, ctx);
  }, []);

  return <canvas ref={surfaceRef} className={className} aria-hidden />;
}
