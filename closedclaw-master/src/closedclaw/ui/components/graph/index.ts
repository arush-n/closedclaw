// Main component
export { MemoryGraph } from "./memory-graph";

// Sub-components
export { Legend } from "./legend";
export { NavigationControls } from "./navigation-controls";
export { NodeDetailPanel } from "./node-detail-panel";
export { GraphCanvas } from "./graph-canvas";
export { Sidebar } from "./sidebar";

// Hooks
export { useForceSimulation } from "./use-force-simulation";
export { useGraphInteractions } from "./use-graph-interactions";

// Constants and utilities
export { colors, getMemoryColor, getMemoryAgeOpacity, FORCE_CONFIG, GRAPH_SETTINGS } from "./constants";

// Types
export type {
  GraphNode,
  GraphEdge,
  MemoryData,
  GraphStats,
  MemoryGraphProps,
  LegendProps,
  NavigationControlsProps,
  GraphCanvasProps,
} from "./types";
