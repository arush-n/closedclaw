"use client";

import { memo, useCallback, useEffect, useLayoutEffect, useRef, useMemo } from "react";
import { colors } from "./constants";
import type { GraphCanvasProps, GraphNode } from "./types";

// Cap DPR to reduce pixel count on retina displays
const MAX_DPR = 1.5;

export const GraphCanvas = memo<GraphCanvasProps>(
  ({
    nodes,
    edges,
    panX,
    panY,
    zoom,
    width,
    height,
    onNodeHover,
    onNodeClick,
    onNodeDragStart,
    onNodeDragMove,
    onNodeDragEnd,
    onPanStart,
    onPanMove,
    onPanEnd,
    onWheel,
    draggingNodeId,
    selectedNodeId = null,
    highlightNodeIds = [],
  }) => {
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const animationRef = useRef<number>(0);
    const mousePos = useRef<{ x: number; y: number }>({ x: 0, y: 0 });
    const currentHoveredNode = useRef<string | null>(null);
    const startTimeRef = useRef<number>(Date.now());
    const nodeMapRef = useRef<Map<string, GraphNode>>(new Map());
    const highlightSet = useMemo(() => new Set(highlightNodeIds), [highlightNodeIds]);
    const canvasMetricsRef = useRef<{ width: number; height: number; dpr: number } | null>(null);

    // Dirty flag — only redraw when something changed
    const dirtyRef = useRef(true);
    const isAnimatingRef = useRef(false);
    const hasNewMemoriesRef = useRef(false);

    // Mark dirty when render-affecting props change
    useEffect(() => {
      dirtyRef.current = true;
    }, [nodes, edges, panX, panY, zoom, width, height, selectedNodeId, highlightSet, draggingNodeId]);

    // Detect new memories (for pulse animation)
    useEffect(() => {
      const now = Date.now();
      hasNewMemoriesRef.current = nodes.some(
        (n) =>
          n.type === "memory" &&
          n.data.created_at &&
          now - new Date(n.data.created_at).getTime() < 24 * 60 * 60 * 1000
      );
    }, [nodes]);

    // Initialize canvas
    useLayoutEffect(() => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.imageSmoothingEnabled = true;
      ctx.imageSmoothingQuality = "low";
    }, []);

    // Spatial grid in WORLD coordinates — only rebuilds when nodes change, not on pan/zoom
    const spatialGrid = useMemo(() => {
      const GRID_CELL_SIZE = 150;
      const grid = new Map<string, GraphNode[]>();

      for (let i = 0; i < nodes.length; i++) {
        const node = nodes[i];
        const cellX = Math.floor(node.x / GRID_CELL_SIZE);
        const cellY = Math.floor(node.y / GRID_CELL_SIZE);
        const cellKey = `${cellX},${cellY}`;

        let bucket = grid.get(cellKey);
        if (!bucket) {
          bucket = [];
          grid.set(cellKey, bucket);
        }
        bucket.push(node);
      }

      return { grid, cellSize: GRID_CELL_SIZE };
    }, [nodes]);

    useEffect(() => {
      const map = new Map<string, GraphNode>();
      for (const node of nodes) {
        map.set(node.id, node);
      }
      nodeMapRef.current = map;
    }, [nodes]);

    // Efficient hit detection — converts screen coords to world coords
    const getNodeAtPosition = useCallback(
      (screenX: number, screenY: number): string | null => {
        const worldX = (screenX - panX) / zoom;
        const worldY = (screenY - panY) / zoom;

        const { grid, cellSize } = spatialGrid;
        const cellX = Math.floor(worldX / cellSize);
        const cellY = Math.floor(worldY / cellSize);

        const cellsToCheck = [
          `${cellX},${cellY}`,
          `${cellX - 1},${cellY}`,
          `${cellX + 1},${cellY}`,
          `${cellX},${cellY - 1}`,
          `${cellX},${cellY + 1}`,
        ];

        for (const key of cellsToCheck) {
          const cellNodes = grid.get(key);
          if (!cellNodes) continue;

          for (let i = cellNodes.length - 1; i >= 0; i--) {
            const node = cellNodes[i]!;
            const dx = worldX - node.x;
            const dy = worldY - node.y;
            const hitRadius = node.size * 1.5;
            if (dx * dx + dy * dy <= hitRadius * hitRadius) {
              return node.id;
            }
          }
        }
        return null;
      },
      [spatialGrid, panX, panY, zoom]
    );

    // Mouse event handlers — throttled hover detection
    const hoverThrottleRef = useRef<number>(0);
    const handleMouseMove = useCallback(
      (e: React.MouseEvent) => {
        const rect = canvasRef.current?.getBoundingClientRect();
        if (!rect) return;

        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        mousePos.current = { x, y };

        if (draggingNodeId) {
          onNodeDragMove(e);
          return;
        }

        // Throttle hover detection to ~30fps
        const now = performance.now();
        if (now - hoverThrottleRef.current < 33) {
          onPanMove(e);
          return;
        }
        hoverThrottleRef.current = now;

        const nodeId = getNodeAtPosition(x, y);
        if (nodeId !== currentHoveredNode.current) {
          currentHoveredNode.current = nodeId;
          dirtyRef.current = true;
          onNodeHover(nodeId);
          if (canvasRef.current) {
            canvasRef.current.style.cursor = nodeId ? "pointer" : "grab";
          }
        }

        onPanMove(e);
      },
      [draggingNodeId, getNodeAtPosition, onNodeHover, onNodeDragMove, onPanMove]
    );

    const handleMouseDown = useCallback(
      (e: React.MouseEvent) => {
        const rect = canvasRef.current?.getBoundingClientRect();
        if (!rect) return;

        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;

        const nodeId = getNodeAtPosition(x, y);
        if (nodeId) {
          onNodeDragStart(nodeId, e);
        } else {
          onPanStart(e);
        }
      },
      [getNodeAtPosition, onNodeDragStart, onPanStart]
    );

    const handleMouseUp = useCallback(
      (e: React.MouseEvent) => {
        const rect = canvasRef.current?.getBoundingClientRect();
        if (!rect) return;

        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;

        if (draggingNodeId) {
          onNodeDragEnd();
        } else {
          const nodeId = getNodeAtPosition(x, y);
          if (nodeId) {
            onNodeClick(nodeId);
          }
          onPanEnd();
        }
      },
      [draggingNodeId, getNodeAtPosition, onNodeClick, onNodeDragEnd, onPanEnd]
    );

    // Draw function — only does work when dirty
    const draw = useCallback(() => {
      const needsAnimation = hasNewMemoriesRef.current || !!draggingNodeId;

      if (!dirtyRef.current && !needsAnimation) {
        if (isAnimatingRef.current) {
          animationRef.current = requestAnimationFrame(draw);
        }
        return;
      }

      dirtyRef.current = false;

      const canvas = canvasRef.current;
      if (!canvas) return;

      const ctx = canvas.getContext("2d");
      if (!ctx) return;

      const dpr = Math.min(window.devicePixelRatio || 1, MAX_DPR);
      const nextCanvasWidth = Math.floor(width * dpr);
      const nextCanvasHeight = Math.floor(height * dpr);
      const previousMetrics = canvasMetricsRef.current;

      if (
        !previousMetrics ||
        previousMetrics.width !== nextCanvasWidth ||
        previousMetrics.height !== nextCanvasHeight ||
        previousMetrics.dpr !== dpr
      ) {
        canvas.width = nextCanvasWidth;
        canvas.height = nextCanvasHeight;
        canvas.style.width = `${width}px`;
        canvas.style.height = `${height}px`;
        canvasMetricsRef.current = { width: nextCanvasWidth, height: nextCanvasHeight, dpr };
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      // Clear
      ctx.fillStyle = colors.background.primary;
      ctx.fillRect(0, 0, width, height);

      // Grid only when zoomed in enough
      if (zoom > 0.5) {
        const gridSize = 24;
        ctx.save();
        ctx.strokeStyle = "rgba(71, 85, 105, 0.06)";
        ctx.lineWidth = 1;
        ctx.beginPath();
        for (let x = 0; x <= width; x += gridSize) {
          ctx.moveTo(x, 0);
          ctx.lineTo(x, height);
        }
        for (let y = 0; y <= height; y += gridSize) {
          ctx.moveTo(0, y);
          ctx.lineTo(width, y);
        }
        ctx.stroke();
        ctx.restore();
      }

      // Viewport bounds for culling
      const pad = 80;

      // Draw edges
      ctx.save();
      for (let i = 0; i < edges.length; i++) {
        const edge = edges[i];
        const sourceNode =
          typeof edge.source === "string" ? nodeMapRef.current.get(edge.source) : edge.source;
        const targetNode =
          typeof edge.target === "string" ? nodeMapRef.current.get(edge.target) : edge.target;

        if (!sourceNode || !targetNode) continue;

        const x1 = sourceNode.x * zoom + panX;
        const y1 = sourceNode.y * zoom + panY;
        const x2 = targetNode.x * zoom + panX;
        const y2 = targetNode.y * zoom + panY;

        // Cull edges fully outside viewport
        if (
          (x1 < -pad && x2 < -pad) ||
          (x1 > width + pad && x2 > width + pad) ||
          (y1 < -pad && y2 < -pad) ||
          (y1 > height + pad && y2 > height + pad)
        ) {
          continue;
        }

        let opacity = edge.visualProps.opacity;
        if (selectedNodeId) {
          const isConnected = sourceNode.id === selectedNodeId || targetNode.id === selectedNodeId;
          opacity = isConnected ? 0.8 : 0.05;
        }

        const dx = x2 - x1;
        const dy = y2 - y1;
        const distance = Math.sqrt(dx * dx + dy * dy);
        const edgeFade = Math.max(0.35, Math.min(1, 280 / Math.max(distance, 1)));
        const edgeOpacity = Math.min(0.9, opacity * edgeFade);

        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.strokeStyle = edge.color.replace(/[\d.]+\)$/, `${edgeOpacity})`);
        ctx.lineWidth = Math.max(0.35, edge.visualProps.thickness * Math.max(zoom, 0.35));
        ctx.stroke();
      }
      ctx.restore();

      // Draw nodes
      const time = (Date.now() - startTimeRef.current) / 1000;

      for (let i = 0; i < nodes.length; i++) {
        const node = nodes[i];
        const screenX = node.x * zoom + panX;
        const screenY = node.y * zoom + panY;
        const nodeSize = node.size * zoom;

        // Cull nodes outside viewport
        if (
          screenX < -nodeSize * 2 || screenX > width + nodeSize * 2 ||
          screenY < -nodeSize * 2 || screenY > height + nodeSize * 2
        ) {
          continue;
        }

        let nodeOpacity = 1;
        if (selectedNodeId && node.id !== selectedNodeId) {
          nodeOpacity = 0.3;
        }

        const isHighlighted = highlightSet.has(node.id);
        const isHovered = currentHoveredNode.current === node.id;
        const isDragging = node.id === draggingNodeId;

        ctx.save();
        ctx.globalAlpha = nodeOpacity;

        // Glow only for interactive nodes
        if (isHighlighted || isHovered || isDragging) {
          const gradient = ctx.createRadialGradient(
            screenX, screenY, nodeSize * 0.4,
            screenX, screenY, nodeSize * 3.4
          );
          gradient.addColorStop(0, node.type === "memory" ? colors.memory.glow : colors.user.glow);
          gradient.addColorStop(1, "transparent");
          ctx.fillStyle = gradient;
          ctx.fillRect(screenX - nodeSize * 2, screenY - nodeSize * 2, nodeSize * 4, nodeSize * 4);
        }

        // Node circle
        ctx.beginPath();
        ctx.arc(screenX, screenY, nodeSize, 0, Math.PI * 2);

        const nodeColor = node.color || (node.type === "memory" ? colors.memory.primary : colors.user.primary);

        if (isHovered || isDragging) {
          const gradient = ctx.createRadialGradient(
            screenX - nodeSize * 0.3, screenY - nodeSize * 0.3, 0,
            screenX, screenY, nodeSize
          );
          gradient.addColorStop(0, nodeColor.replace(/([\d.]+)\)$/, "0.95)"));
          gradient.addColorStop(1, nodeColor);
          ctx.fillStyle = gradient;
        } else {
          ctx.fillStyle = nodeColor;
        }
        ctx.fill();

        // Border
        ctx.strokeStyle = node.type === "memory" ? colors.memory.border : colors.user.border;
        ctx.lineWidth = isHovered || isDragging ? 1.2 : 0.8;
        ctx.stroke();

        // Pulse for new memories (subtle)
        if (node.type === "memory" && node.data.created_at) {
          const ageMs = Date.now() - new Date(node.data.created_at).getTime();
          if (ageMs < 24 * 60 * 60 * 1000) {
            const pulsePhase = (time * 1.5) % 1; // Slower pulse
            const pulseRadius = nodeSize * (1 + pulsePhase * 0.3); // Smaller pulse
            const pulseOpacity = 0.2 * (1 - pulsePhase);

            ctx.beginPath();
            ctx.arc(screenX, screenY, pulseRadius, 0, Math.PI * 2);
            ctx.strokeStyle = colors.status.new.replace(/[\d.]+\)$/, `${pulseOpacity})`);
            ctx.lineWidth = 1.5;
            ctx.stroke();
            dirtyRef.current = true;
          }
        }

        if (node.type === "user") {
          ctx.beginPath();
          ctx.arc(screenX, screenY, Math.max(1.2, nodeSize * 0.32), 0, Math.PI * 2);
          ctx.fillStyle = "rgba(209, 250, 229, 0.95)";
          ctx.fill();
        }

        ctx.restore();
      }

      if (isAnimatingRef.current) {
        animationRef.current = requestAnimationFrame(draw);
      }
    }, [nodes, edges, panX, panY, zoom, width, height, selectedNodeId, highlightSet, draggingNodeId]);

    // Start/stop animation loop
    useEffect(() => {
      startTimeRef.current = Date.now();
      isAnimatingRef.current = true;
      dirtyRef.current = true;
      animationRef.current = requestAnimationFrame(draw);
      return () => {
        isAnimatingRef.current = false;
        if (animationRef.current) {
          cancelAnimationFrame(animationRef.current);
        }
      };
    }, [draw]);

    // Attach wheel listener natively with passive:false
    useEffect(() => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const handler = (e: WheelEvent) => {
        e.preventDefault();
        e.stopPropagation();
        onWheel(e as unknown as React.WheelEvent);
      };
      canvas.addEventListener("wheel", handler, { passive: false });
      return () => canvas.removeEventListener("wheel", handler);
    }, [onWheel]);

    return (
      <canvas
        ref={canvasRef}
        className="absolute inset-0 cursor-grab active:cursor-grabbing"
        onMouseMove={handleMouseMove}
        onMouseDown={handleMouseDown}
        onMouseUp={handleMouseUp}
        onMouseLeave={() => {
          onPanEnd();
          onNodeHover(null);
        }}
      />
    );
  }
);

GraphCanvas.displayName = "GraphCanvas";
