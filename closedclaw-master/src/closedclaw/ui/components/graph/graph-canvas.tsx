"use client";

import { memo, useCallback, useEffect, useLayoutEffect, useRef, useMemo } from "react";
import { colors } from "./constants";
import type { GraphCanvasProps, GraphNode } from "./types";

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

    // Initialize canvas quality
    useLayoutEffect(() => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.imageSmoothingEnabled = true;
      ctx.imageSmoothingQuality = "high";
    }, []);

    // Spatial grid for optimized hit detection
    const spatialGrid = useMemo(() => {
      const GRID_CELL_SIZE = 150;
      const grid = new Map<string, GraphNode[]>();

      nodes.forEach((node) => {
        const screenX = node.x * zoom + panX;
        const screenY = node.y * zoom + panY;
        const cellX = Math.floor(screenX / GRID_CELL_SIZE);
        const cellY = Math.floor(screenY / GRID_CELL_SIZE);
        const cellKey = `${cellX},${cellY}`;

        if (!grid.has(cellKey)) {
          grid.set(cellKey, []);
        }
        grid.get(cellKey)!.push(node);
      });

      return { grid, cellSize: GRID_CELL_SIZE };
    }, [nodes, panX, panY, zoom]);

    useEffect(() => {
      const map = new Map<string, GraphNode>();
      for (const node of nodes) {
        map.set(node.id, node);
      }
      nodeMapRef.current = map;
    }, [nodes]);

    // Efficient hit detection
    const getNodeAtPosition = useCallback(
      (x: number, y: number): string | null => {
        const { grid, cellSize } = spatialGrid;
        const cellX = Math.floor(x / cellSize);
        const cellY = Math.floor(y / cellSize);

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
            const screenX = node.x * zoom + panX;
            const screenY = node.y * zoom + panY;
            const nodeSize = node.size * zoom;

            const dx = x - screenX;
            const dy = y - screenY;
            if (dx * dx + dy * dy <= nodeSize * nodeSize) {
              return node.id;
            }
          }
        }
        return null;
      },
      [spatialGrid, panX, panY, zoom]
    );

    // Mouse event handlers
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

        const nodeId = getNodeAtPosition(x, y);
        if (nodeId !== currentHoveredNode.current) {
          currentHoveredNode.current = nodeId;
          onNodeHover(nodeId);
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

    // Draw function
    const draw = useCallback(() => {
      const canvas = canvasRef.current;
      if (!canvas) return;

      const ctx = canvas.getContext("2d");
      if (!ctx) return;

      const dpr = window.devicePixelRatio || 1;
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
        canvasMetricsRef.current = {
          width: nextCanvasWidth,
          height: nextCanvasHeight,
          dpr,
        };
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      // Clear canvas
      const bgGradient = ctx.createRadialGradient(
        width * 0.5,
        height * 0.45,
        Math.min(width, height) * 0.06,
        width * 0.5,
        height * 0.5,
        Math.max(width, height) * 0.72
      );
      bgGradient.addColorStop(0, "#0b1428");
      bgGradient.addColorStop(0.55, colors.background.secondary);
      bgGradient.addColorStop(1, colors.background.primary);
      ctx.fillStyle = bgGradient;
      ctx.fillRect(0, 0, width, height);

      const gridSize = 24;
      ctx.save();
      ctx.strokeStyle = "rgba(71, 85, 105, 0.12)";
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

      // Draw edges first (behind nodes)
      ctx.save();
      edges.forEach((edge) => {
        const sourceNode = typeof edge.source === "string" 
          ? nodeMapRef.current.get(edge.source)
          : edge.source;
        const targetNode = typeof edge.target === "string"
          ? nodeMapRef.current.get(edge.target)
          : edge.target;

        if (!sourceNode || !targetNode) return;

        const x1 = sourceNode.x * zoom + panX;
        const y1 = sourceNode.y * zoom + panY;
        const x2 = targetNode.x * zoom + panX;
        const y2 = targetNode.y * zoom + panY;

        // Skip edges outside viewport
        if (
          (x1 < -50 && x2 < -50) ||
          (x1 > width + 50 && x2 > width + 50) ||
          (y1 < -50 && y2 < -50) ||
          (y1 > height + 50 && y2 > height + 50)
        ) {
          return;
        }

        // Determine edge opacity based on selection
        let opacity = edge.visualProps.opacity;
        if (selectedNodeId) {
          const isConnected =
            sourceNode.id === selectedNodeId || targetNode.id === selectedNodeId;
          opacity = isConnected ? 0.8 : 0.1;
        }

        const dx = x2 - x1;
        const dy = y2 - y1;
        const distance = Math.hypot(dx, dy);
        const edgeFade = Math.max(0.35, Math.min(1, 280 / Math.max(distance, 1)));
        const edgeOpacity = Math.min(0.9, opacity * edgeFade);

        const edgeGradient = ctx.createLinearGradient(x1, y1, x2, y2);
        edgeGradient.addColorStop(0, edge.color.replace(/[\d.]+\)$/, `${edgeOpacity})`));
        edgeGradient.addColorStop(0.5, edge.color.replace(/[\d.]+\)$/, `${Math.min(0.95, edgeOpacity + 0.1)})`));
        edgeGradient.addColorStop(1, edge.color.replace(/[\d.]+\)$/, `${edgeOpacity})`));

        // Draw edge
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.strokeStyle = edgeGradient;
        ctx.lineWidth = Math.max(0.35, edge.visualProps.thickness * Math.max(zoom, 0.35));
        ctx.stroke();
      });
      ctx.restore();

      // Draw nodes
      const time = (Date.now() - startTimeRef.current) / 1000;
      
      nodes.forEach((node) => {
        const screenX = node.x * zoom + panX;
        const screenY = node.y * zoom + panY;
        const nodeSize = node.size * zoom;

        // Skip nodes outside viewport
        if (
          screenX < -nodeSize ||
          screenX > width + nodeSize ||
          screenY < -nodeSize ||
          screenY > height + nodeSize
        ) {
          return;
        }

        // Determine node opacity based on selection
        let nodeOpacity = 1;
        if (selectedNodeId && node.id !== selectedNodeId) {
          nodeOpacity = 0.3;
        }

        const isHighlighted = highlightSet.has(node.id);
        const isHovered = currentHoveredNode.current === node.id;
        const isDragging = node.id === draggingNodeId;

        ctx.save();
        ctx.globalAlpha = nodeOpacity;

        // Draw glow for highlighted/hovered nodes
        if (isHighlighted || isHovered || isDragging) {
          const gradient = ctx.createRadialGradient(
            screenX,
            screenY,
            nodeSize * 0.4,
            screenX,
            screenY,
            nodeSize * 3.4
          );
          gradient.addColorStop(0, node.type === "memory" ? colors.memory.glow : colors.user.glow);
          gradient.addColorStop(1, "transparent");
          ctx.fillStyle = gradient;
          ctx.fillRect(
            screenX - nodeSize * 2,
            screenY - nodeSize * 2,
            nodeSize * 4,
            nodeSize * 4
          );
        }

        // Draw node circle
        ctx.beginPath();
        ctx.arc(screenX, screenY, nodeSize, 0, Math.PI * 2);
        
        // Fill with gradient
        const nodeColor = node.color || (node.type === "memory" ? colors.memory.primary : colors.user.primary);
        const gradient = ctx.createRadialGradient(
          screenX - nodeSize * 0.3,
          screenY - nodeSize * 0.3,
          0,
          screenX,
          screenY,
          nodeSize
        );
        gradient.addColorStop(0, nodeColor.replace(/([\d.]+)\)$/, "0.95)"));
        gradient.addColorStop(1, nodeColor);
        ctx.fillStyle = gradient;
        ctx.fill();

        // Draw border
        ctx.strokeStyle = node.type === "memory" ? colors.memory.border : colors.user.border;
        ctx.lineWidth = isHovered || isDragging ? 1.2 : 0.8;
        ctx.stroke();

        // Draw pulse animation for new memories
        if (node.type === "memory" && node.data.created_at) {
          const ageMs = Date.now() - new Date(node.data.created_at).getTime();
          if (ageMs < 24 * 60 * 60 * 1000) {
            // Pulse for new memories
            const pulsePhase = (time * 2) % 1;
            const pulseRadius = nodeSize * (1 + pulsePhase * 0.5);
            const pulseOpacity = 0.3 * (1 - pulsePhase);
            
            ctx.beginPath();
            ctx.arc(screenX, screenY, pulseRadius, 0, Math.PI * 2);
            ctx.strokeStyle = colors.status.new.replace(/[\d.]+\)$/, `${pulseOpacity})`);
            ctx.lineWidth = 2;
            ctx.stroke();
          }
        }

        if (node.type === "user") {
          ctx.beginPath();
          ctx.arc(screenX, screenY, Math.max(1.2, nodeSize * 0.32), 0, Math.PI * 2);
          ctx.fillStyle = "rgba(209, 250, 229, 0.95)";
          ctx.fill();
        }

        ctx.restore();
      });

      // Continue animation
      animationRef.current = requestAnimationFrame(draw);
    }, [
      nodes,
      edges,
      panX,
      panY,
      zoom,
      width,
      height,
      selectedNodeId,
      highlightSet,
      draggingNodeId,
    ]);

    // Start animation loop
    useEffect(() => {
      startTimeRef.current = Date.now();
      animationRef.current = requestAnimationFrame(draw);
      return () => {
        if (animationRef.current) {
          cancelAnimationFrame(animationRef.current);
        }
      };
    }, [draw]);

    return (
      <canvas
        ref={canvasRef}
        className="absolute inset-0 cursor-grab active:cursor-grabbing"
        onMouseMove={handleMouseMove}
        onMouseDown={handleMouseDown}
        onMouseUp={handleMouseUp}
        onMouseLeave={(e) => {
          onPanEnd();
          onNodeHover(null);
        }}
        onWheel={onWheel}
      />
    );
  }
);

GraphCanvas.displayName = "GraphCanvas";
