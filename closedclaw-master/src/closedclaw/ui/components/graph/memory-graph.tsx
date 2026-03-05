"use client";

import { memo, useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import { GraphCanvas } from "./graph-canvas";
import { Legend } from "./legend";
import { NavigationControls } from "./navigation-controls";
import { NodeDetailPanel } from "./node-detail-panel";
import { NodeHoverTooltip } from "./node-hover-tooltip";
import { useForceSimulation } from "./use-force-simulation";
import { useGraphInteractions } from "./use-graph-interactions";
import { colors, getMemoryColor, getMemoryAgeOpacity, NODE_SIZES, SIMILARITY_CONFIG } from "./constants";
import type {
  MemoryGraphProps,
  GraphNode,
  GraphEdge,
  MemoryData,
  GraphStats,
} from "./types";

// Generate unique edge ID
function edgeId(sourceId: string, targetId: string): string {
  return sourceId < targetId ? `${sourceId}-${targetId}` : `${targetId}-${sourceId}`;
}

function hashToUnit(value: string, salt = 0): number {
  let hash = 2166136261 ^ salt;
  for (let i = 0; i < value.length; i++) {
    hash ^= value.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0) / 4294967295;
}

function tokenizeText(text?: string): string[] {
  if (!text) return [];
  return text
    .toLowerCase()
    .split(/\W+/)
    .filter((token) => token.length > 2);
}

// Derive a group label from memory categories
const GROUP_MAPPINGS: Record<string, string> = {
  work: "Work",
  project: "Work",
  programming: "Dev",
  tools: "Dev",
  code: "Dev",
  personal: "Personal",
  life: "Personal",
  preference: "Preferences",
  like: "Preferences",
  knowledge: "Knowledge",
  learn: "Knowledge",
  learning: "Knowledge",
  research: "Knowledge",
  interest: "Interests",
  ai: "Interests",
  relationship: "People",
  person: "People",
  design: "Design",
  visualization: "Design",
  databases: "Dev",
  "machine-learning": "Knowledge",
  scale: "System",
  autoseed: "System",
};

function deriveGroup(categories?: string[]): string {
  if (!categories || categories.length === 0) return "Uncategorized";
  for (const cat of categories) {
    const key = cat.toLowerCase();
    if (GROUP_MAPPINGS[key]) return GROUP_MAPPINGS[key];
    // Partial match
    for (const [pattern, group] of Object.entries(GROUP_MAPPINGS)) {
      if (key.includes(pattern)) return group;
    }
  }
  return "Other";
}

function calculateTokenSimilarity(words1: Set<string>, words2: Set<string>): number {
  if (words1.size === 0 || words2.size === 0) return 0;

  let intersection = 0;
  const smaller = words1.size <= words2.size ? words1 : words2;
  const larger = smaller === words1 ? words2 : words1;

  for (const word of smaller) {
    if (larger.has(word)) {
      intersection += 1;
    }
  }

  const union = words1.size + words2.size - intersection;
  if (union === 0) return 0;
  return intersection / union;
}

// Build graph data from memories
function buildGraphData(
  memories: MemoryData[],
  similarityThreshold: number
): { nodes: GraphNode[]; edges: GraphEdge[]; stats: GraphStats } {
  const safeMemories = memories
    .map((memory) => {
      const normalizedText =
        memory.memory ||
        ((memory as unknown as { content?: string }).content ?? "") ||
        "";
      if (!normalizedText.trim()) {
        return null;
      }

      const normalizedCategories =
        memory.categories ??
        ((memory as unknown as { tags?: string[] }).tags ?? []);

      return {
        ...memory,
        memory: normalizedText,
        categories: normalizedCategories,
      } as MemoryData;
    })
    .filter((memory): memory is MemoryData => Boolean(memory));

  const nodes: GraphNode[] = [];
  const edges: GraphEdge[] = [];
  const userNodes = new Map<string, GraphNode>();
  const categories: Record<string, number> = {};
  const groups: Record<string, number> = {};
  const tokenSets = safeMemories.map((memory) => new Set(tokenizeText(memory.memory)));
  const tokenIndex = new Map<string, number[]>();

  tokenSets.forEach((tokens, idx) => {
    tokens.forEach((token) => {
      const bucket = tokenIndex.get(token);
      if (bucket) {
        bucket.push(idx);
      } else {
        tokenIndex.set(token, [idx]);
      }
    });
  });

  // Create memory nodes
  safeMemories.forEach((memory, index) => {
    const angle = hashToUnit(memory.id, index) * Math.PI * 2;
    const radius = 200 + hashToUnit(memory.id, index + 17) * 150;
    
    // Count categories
    memory.categories?.forEach(cat => {
      categories[cat] = (categories[cat] || 0) + 1;
    });

    // Assign group
    const group = deriveGroup(memory.categories);
    memory.group = group;
    groups[group] = (groups[group] || 0) + 1;

    const node: GraphNode = {
      id: memory.id,
      type: "memory",
      x: Math.cos(angle) * radius,
      y: Math.sin(angle) * radius,
      data: memory,
      size: NODE_SIZES.memory.default,
      color: getMemoryColor(memory.categories),
      isHovered: false,
      isDragging: false,
    };
    nodes.push(node);

    // Create user node if not exists
    if (memory.user_id && !userNodes.has(memory.user_id)) {
      const userAngle = hashToUnit(memory.user_id, 31) * Math.PI * 2;
      const userNode: GraphNode = {
        id: `user-${memory.user_id}`,
        type: "user",
        x: Math.cos(userAngle) * 400,
        y: Math.sin(userAngle) * 400,
        data: {
          id: memory.user_id,
          memory: `User: ${memory.user_id}`,
          user_id: memory.user_id,
        },
        size: NODE_SIZES.user.default,
        color: colors.user.primary,
        isHovered: false,
        isDragging: false,
      };
      userNodes.set(memory.user_id, userNode);
      nodes.push(userNode);
    }

    // Connect memory to user
    if (memory.user_id) {
      const edge: GraphEdge = {
        id: edgeId(memory.id, `user-${memory.user_id}`),
        source: memory.id,
        target: `user-${memory.user_id}`,
        similarity: 1,
        edgeType: "memory-user",
        visualProps: {
          opacity: 0.3,
          thickness: 1,
          glow: 0,
        },
        color: colors.connection.medium,
      };
      edges.push(edge);
    }
  });

  // Create similarity edges between memories
  const edgeSet = new Set<string>();
  for (let i = 0; i < safeMemories.length; i++) {
    const candidateScores = new Map<number, number>();
    tokenSets[i]?.forEach((token) => {
      const matches = tokenIndex.get(token);
      if (!matches) return;
      for (const candidateIndex of matches) {
        if (candidateIndex <= i) continue;
        candidateScores.set(
          candidateIndex,
          (candidateScores.get(candidateIndex) || 0) + 1
        );
      }
    });

    const topCandidates = Array.from(candidateScores.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, SIMILARITY_CONFIG.maxComparisonsPerNode * 3)
      .map(([candidateIndex]) => candidateIndex);

    const wordsI = tokenSets[i] || new Set<string>();
    let comparisons = 0;
    for (const j of topCandidates) {
      if (comparisons >= SIMILARITY_CONFIG.maxComparisonsPerNode) {
        break;
      }

      const similarity = calculateTokenSimilarity(wordsI, tokenSets[j] || new Set<string>());
      comparisons += 1;

      if (similarity >= similarityThreshold) {
        const id = edgeId(safeMemories[i].id, safeMemories[j].id);
        if (!edgeSet.has(id)) {
          edgeSet.add(id);
          edges.push({
            id,
            source: safeMemories[i].id,
            target: safeMemories[j].id,
            similarity,
            edgeType: "similarity",
            visualProps: {
              opacity: 0.1 + similarity * 0.5,
              thickness: 0.5 + similarity * 1.5,
              glow: similarity > 0.7 ? 0.3 : 0,
            },
            color:
              similarity > 0.7
                ? colors.connection.strong
                : similarity > 0.4
                ? colors.connection.medium
                : colors.connection.weak,
          });
        }
      }
    }
  }

  const stats: GraphStats = {
    totalMemories: safeMemories.length,
    totalUsers: userNodes.size,
    totalConnections: edges.length,
    categories,
    groups,
  };

  return { nodes, edges, stats };
}

export const MemoryGraph = memo<MemoryGraphProps>(function MemoryGraph({
  memories,
  isLoading = false,
  error = null,
  onMemoryClick,
  onMemoryHover,
  className = "",
  showLegend = true,
  showControls = true,
  similarityThreshold = SIMILARITY_CONFIG.threshold,
  activeGroup = null,
  onGroupsChange,
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerSize, setContainerSize] = useState({ width: 0, height: 0 });
  const [hasAutoFitted, setHasAutoFitted] = useState(false);
  const [hoverTooltip, setHoverTooltip] = useState<{ node: GraphNode; x: number; y: number } | null>(null);
  const mousePosRef = useRef({ x: 0, y: 0 });

  // Graph interactions
  const {
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
  } = useGraphInteractions();

  // Build graph data
  const { nodes, edges, stats } = useMemo(() => {
    const result = buildGraphData(memories, similarityThreshold);
    if (!activeGroup) return result;
    // Filter nodes by group
    const filteredNodeIds = new Set(
      result.nodes
        .filter((n) => n.type === "user" || n.data.group === activeGroup)
        .map((n) => n.id)
    );
    return {
      nodes: result.nodes.filter((n) => filteredNodeIds.has(n.id)),
      edges: result.edges.filter((e) => {
        const sourceId = typeof e.source === "string" ? e.source : e.source.id;
        const targetId = typeof e.target === "string" ? e.target : e.target.id;
        return filteredNodeIds.has(sourceId) && filteredNodeIds.has(targetId);
      }),
      stats: result.stats,
    };
  }, [memories, similarityThreshold, activeGroup]);

  // Report groups to parent
  useEffect(() => {
    if (onGroupsChange && stats.groups) {
      onGroupsChange(stats.groups);
    }
  }, [stats.groups, onGroupsChange]);

  // Force simulation
  const [, forceRender] = useReducer((x: number) => x + 1, 0);
  const forceSimulation = useForceSimulation(
    nodes,
    edges,
    forceRender,
    true
  );

  // Resize observer
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const resizeObserver = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry) {
        const { width, height } = entry.contentRect;
        setContainerSize({ width, height });
      }
    });

    resizeObserver.observe(container);
    return () => resizeObserver.disconnect();
  }, []);

  // Auto-fit on initial load
  useEffect(() => {
    if (
      !hasAutoFitted &&
      nodes.length > 0 &&
      containerSize.width > 0 &&
      containerSize.height > 0
    ) {
      // Wait for simulation to settle a bit
      const timer = setTimeout(() => {
        fitToViewport(nodes, containerSize.width, containerSize.height);
        setHasAutoFitted(true);
      }, 500);
      return () => clearTimeout(timer);
    }
  }, [nodes, containerSize, hasAutoFitted, fitToViewport]);

  // Handle node interactions
  const handleNodeHoverWithCallback = useCallback(
    (nodeId: string | null) => {
      handleNodeHover(nodeId);
      if (nodeId) {
        const node = nodes.find((n) => n.id === nodeId);
        if (node) {
          setHoverTooltip({ node, x: mousePosRef.current.x, y: mousePosRef.current.y });
        }
      } else {
        setHoverTooltip(null);
      }
      if (onMemoryHover) {
        const node = nodes.find((n) => n.id === nodeId);
        onMemoryHover(node?.data || null);
      }
    },
    [handleNodeHover, nodes, onMemoryHover]
  );

  const handleNodeClickWithCallback = useCallback(
    (nodeId: string) => {
      handleNodeClick(nodeId, nodes);
      if (onMemoryClick) {
        const node = nodes.find((n) => n.id === nodeId);
        if (node && node.type === "memory") {
          onMemoryClick(node.data);
        }
      }
    },
    [handleNodeClick, nodes, onMemoryClick]
  );

  const handleNodeDragStartWithReheat = useCallback(
    (nodeId: string, e: React.MouseEvent) => {
      handleNodeDragStart(nodeId, e, nodes);
      forceSimulation.reheat();
    },
    [handleNodeDragStart, nodes, forceSimulation]
  );

  const handleNodeDragEndWithCooldown = useCallback(() => {
    handleNodeDragEnd();
    forceSimulation.coolDown();
  }, [handleNodeDragEnd, forceSimulation]);

  const handleFitToView = useCallback(() => {
    fitToViewport(nodes, containerSize.width, containerSize.height);
  }, [fitToViewport, nodes, containerSize]);

  // Error state — show as overlay instead of blocking
  if (error) {
    return (
      <div className={`relative w-full h-full bg-zinc-950 flex items-center justify-center ${className}`}>
        <div className="text-center space-y-4">
          <p className="text-red-400">Error loading memories</p>
          <p className="text-zinc-500 text-sm">{error.message}</p>
        </div>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className={`relative w-full h-full bg-zinc-950 overflow-hidden ${className}`}
      onMouseMove={(e) => {
        const rect = containerRef.current?.getBoundingClientRect();
        if (rect) {
          mousePosRef.current = { x: e.clientX - rect.left, y: e.clientY - rect.top };
          if (hoverTooltip) {
            setHoverTooltip((prev) => prev ? { ...prev, x: mousePosRef.current.x, y: mousePosRef.current.y } : null);
          }
        }
      }}
    >
      {/* Loading overlay */}
      {isLoading && memories.length === 0 && (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-zinc-950/80 backdrop-blur-sm">
          <div className="text-center space-y-3">
            <div className="w-10 h-10 border-3 border-zinc-700 border-t-violet-500 rounded-full animate-spin mx-auto" />
            <p className="text-slate-400 text-sm">Loading memories...</p>
          </div>
        </div>
      )}

      {/* Empty state overlay */}
      {!isLoading && memories.length === 0 && (
        <div className="absolute inset-0 z-10 flex items-center justify-center">
          <div className="text-center space-y-3">
            <div className="w-14 h-14 rounded-full bg-zinc-800/50 flex items-center justify-center mx-auto">
              <svg className="w-7 h-7 text-zinc-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
              </svg>
            </div>
            <p className="text-slate-400 text-sm">No memories yet</p>
            <p className="text-slate-500 text-xs">Add some memories to see them visualized here</p>
          </div>
        </div>
      )}

      {/* Graph Canvas */}
      <GraphCanvas
        nodes={nodes}
        edges={edges}
        panX={panX}
        panY={panY}
        zoom={zoom}
        width={containerSize.width}
        height={containerSize.height}
        onNodeHover={handleNodeHoverWithCallback}
        onNodeClick={handleNodeClickWithCallback}
        onNodeDragStart={handleNodeDragStartWithReheat}
        onNodeDragMove={handleNodeDragMove}
        onNodeDragEnd={handleNodeDragEndWithCooldown}
        onPanStart={handlePanStart}
        onPanMove={handlePanMove}
        onPanEnd={handlePanEnd}
        onWheel={handleWheel}
        draggingNodeId={draggingNodeId}
        selectedNodeId={selectedNode?.id || null}
      />

      {/* Node Detail Panel */}
      <NodeDetailPanel
        node={selectedNode}
        onClose={() => setSelectedNode(null)}
      />

      {/* Hover Tooltip */}
      {!selectedNode && hoverTooltip && (
        <NodeHoverTooltip
          node={hoverTooltip.node}
          x={hoverTooltip.x}
          y={hoverTooltip.y}
          containerWidth={containerSize.width}
          containerHeight={containerSize.height}
        />
      )}

      {/* Legend */}
      {showLegend && <Legend stats={stats} isLoading={isLoading} />}

      {/* Navigation Controls */}
      {showControls && (
        <NavigationControls
          onZoomIn={zoomIn}
          onZoomOut={zoomOut}
          onFitToView={handleFitToView}
          onResetView={resetView}
          zoom={zoom}
        />
      )}
    </div>
  );
});

MemoryGraph.displayName = "MemoryGraph";
