"use client";

import { useCallback, useRef, useState } from "react";
import { GRAPH_SETTINGS } from "./constants";
import type { GraphNode } from "./types";

export interface GraphInteractionsState {
  panX: number;
  panY: number;
  zoom: number;
  hoveredNode: string | null;
  selectedNode: GraphNode | null;
  draggingNodeId: string | null;
  nodePositions: Map<string, { x: number; y: number }>;
}

export interface GraphInteractionsHandlers {
  handlePanStart: (e: React.MouseEvent) => void;
  handlePanMove: (e: React.MouseEvent) => void;
  handlePanEnd: () => void;
  handleWheel: (e: React.WheelEvent) => void;
  handleNodeHover: (nodeId: string | null) => void;
  handleNodeClick: (nodeId: string, nodes: GraphNode[]) => void;
  handleNodeDragStart: (nodeId: string, e: React.MouseEvent, nodes: GraphNode[]) => void;
  handleNodeDragMove: (e: React.MouseEvent) => void;
  handleNodeDragEnd: () => void;
  zoomIn: () => void;
  zoomOut: () => void;
  resetView: () => void;
  fitToViewport: (nodes: GraphNode[], width: number, height: number) => void;
  setSelectedNode: (node: GraphNode | null) => void;
}

export function useGraphInteractions(): GraphInteractionsState & GraphInteractionsHandlers {
  const [panX, setPanX] = useState(0);
  const [panY, setPanY] = useState(0);
  const [zoom, setZoom] = useState(GRAPH_SETTINGS.initialZoom);
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [draggingNodeId, setDraggingNodeId] = useState<string | null>(null);
  const [nodePositions] = useState<Map<string, { x: number; y: number }>>(new Map());

  const isPanning = useRef(false);
  const lastMousePos = useRef({ x: 0, y: 0 });
  const draggedNode = useRef<GraphNode | null>(null);
  const dragStartPos = useRef({ x: 0, y: 0 });

  // Refs for current values to avoid stale closures in RAF callbacks
  const panRef = useRef({ x: 0, y: 0 });
  const zoomRef = useRef(GRAPH_SETTINGS.initialZoom);
  const panRafId = useRef<number | null>(null);
  const zoomRafId = useRef<number | null>(null);

  const handlePanStart = useCallback((e: React.MouseEvent) => {
    if (draggingNodeId) return;
    isPanning.current = true;
    lastMousePos.current = { x: e.clientX, y: e.clientY };
  }, [draggingNodeId]);

  const handlePanMove = useCallback((e: React.MouseEvent) => {
    if (!isPanning.current) return;

    const dx = e.clientX - lastMousePos.current.x;
    const dy = e.clientY - lastMousePos.current.y;
    lastMousePos.current = { x: e.clientX, y: e.clientY };

    // Accumulate in ref, flush via RAF to batch updates
    panRef.current.x += dx;
    panRef.current.y += dy;

    if (panRafId.current === null) {
      panRafId.current = requestAnimationFrame(() => {
        const accumulated = panRef.current;
        setPanX((prev) => prev + accumulated.x);
        setPanY((prev) => prev + accumulated.y);
        panRef.current = { x: 0, y: 0 };
        panRafId.current = null;
      });
    }
  }, []);

  const handlePanEnd = useCallback(() => {
    isPanning.current = false;
  }, []);

  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();

    const rect = e.currentTarget.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    const zoomFactor = e.deltaY > 0 ? 0.9 : 1.1;

    // Use functional updates to avoid stale closure on zoom/panX/panY
    setZoom((prevZoom) => {
      const newZoom = Math.max(
        GRAPH_SETTINGS.minZoom,
        Math.min(GRAPH_SETTINGS.maxZoom, prevZoom * zoomFactor)
      );
      const scaleDiff = newZoom - prevZoom;

      setPanX((prevPanX) => prevPanX - (mouseX - prevPanX) * (scaleDiff / prevZoom));
      setPanY((prevPanY) => prevPanY - (mouseY - prevPanY) * (scaleDiff / prevZoom));

      return newZoom;
    });
  }, []);

  const handleNodeHover = useCallback((nodeId: string | null) => {
    setHoveredNode(nodeId);
  }, []);

  const handleNodeClick = useCallback((nodeId: string, nodes: GraphNode[]) => {
    const node = nodes.find((n) => n.id === nodeId);
    if (node) {
      setSelectedNode(node);
    }
  }, []);

  const handleNodeDragStart = useCallback(
    (nodeId: string, e: React.MouseEvent, nodes: GraphNode[]) => {
      const node = nodes.find((n) => n.id === nodeId);
      if (!node) return;

      setDraggingNodeId(nodeId);
      draggedNode.current = node;
      dragStartPos.current = { x: e.clientX, y: e.clientY };

      // Fix the node position during drag
      node.fx = node.x;
      node.fy = node.y;
    },
    []
  );

  const handleNodeDragMove = useCallback(
    (e: React.MouseEvent) => {
      if (!draggedNode.current) return;

      const dx = (e.clientX - dragStartPos.current.x) / zoom;
      const dy = (e.clientY - dragStartPos.current.y) / zoom;

      draggedNode.current.fx = draggedNode.current.x + dx;
      draggedNode.current.fy = draggedNode.current.y + dy;
      draggedNode.current.x = draggedNode.current.fx;
      draggedNode.current.y = draggedNode.current.fy;

      dragStartPos.current = { x: e.clientX, y: e.clientY };
    },
    [zoom]
  );

  const handleNodeDragEnd = useCallback(() => {
    if (draggedNode.current) {
      // Release the fixed position
      draggedNode.current.fx = null;
      draggedNode.current.fy = null;
    }
    draggedNode.current = null;
    setDraggingNodeId(null);
  }, []);

  const zoomIn = useCallback(() => {
    setZoom((prev) =>
      Math.min(GRAPH_SETTINGS.maxZoom, prev + GRAPH_SETTINGS.zoomStep)
    );
  }, []);

  const zoomOut = useCallback(() => {
    setZoom((prev) =>
      Math.max(GRAPH_SETTINGS.minZoom, prev - GRAPH_SETTINGS.zoomStep)
    );
  }, []);

  const resetView = useCallback(() => {
    setZoom(GRAPH_SETTINGS.initialZoom);
    setPanX(0);
    setPanY(0);
  }, []);

  const fitToViewport = useCallback(
    (nodes: GraphNode[], width: number, height: number) => {
      if (nodes.length === 0) return;

      // Calculate bounding box in a single pass
      let minX = Infinity,
        maxX = -Infinity,
        minY = Infinity,
        maxY = -Infinity;

      for (let i = 0; i < nodes.length; i++) {
        const node = nodes[i];
        if (node.x < minX) minX = node.x;
        if (node.x > maxX) maxX = node.x;
        if (node.y < minY) minY = node.y;
        if (node.y > maxY) maxY = node.y;
      }

      const graphWidth = maxX - minX + 200;
      const graphHeight = maxY - minY + 200;

      const scaleX = width / graphWidth;
      const scaleY = height / graphHeight;
      const newZoom = Math.min(scaleX, scaleY, GRAPH_SETTINGS.maxZoom) * 0.9;

      const centerX = (minX + maxX) / 2;
      const centerY = (minY + maxY) / 2;

      setZoom(newZoom);
      setPanX(width / 2 - centerX * newZoom);
      setPanY(height / 2 - centerY * newZoom);
    },
    []
  );

  return {
    panX,
    panY,
    zoom,
    hoveredNode,
    selectedNode,
    draggingNodeId,
    nodePositions,
    handlePanStart,
    handlePanMove,
    handlePanEnd,
    handleWheel,
    handleNodeHover,
    handleNodeClick,
    handleNodeDragStart,
    handleNodeDragMove,
    handleNodeDragEnd,
    zoomIn,
    zoomOut,
    resetView,
    fitToViewport,
    setSelectedNode,
  };
}
