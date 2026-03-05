// Graph node types
export interface GraphNode {
  id: string;
  type: "memory" | "document" | "user";
  x: number;
  y: number;
  data: MemoryData;
  size: number;
  color: string;
  isHovered: boolean;
  isDragging: boolean;
  // D3-force simulation properties
  vx?: number;
  vy?: number;
  fx?: number | null;
  fy?: number | null;
}

export interface MemoryData {
  id: string;
  memory: string;
  hash?: string;
  user_id?: string;
  agent_id?: string;
  metadata?: Record<string, unknown>;
  categories?: string[];
  created_at?: string;
  updated_at?: string;
  custom_categories?: string[];
  score?: number;
  sensitivity?: number;
  encrypted?: boolean;
  group?: string;
}

export type EdgeType = "memory-memory" | "memory-user" | "similarity";

export interface GraphEdge {
  id: string;
  source: string | GraphNode;
  target: string | GraphNode;
  similarity: number;
  edgeType: EdgeType;
  visualProps: {
    opacity: number;
    thickness: number;
    glow: number;
  };
  color: string;
}

export interface GraphStats {
  totalMemories: number;
  totalUsers: number;
  totalConnections: number;
  categories: Record<string, number>;
  groups: Record<string, number>;
}

export interface MemoryGraphProps {
  memories: MemoryData[];
  isLoading?: boolean;
  error?: Error | null;
  onMemoryClick?: (memory: MemoryData) => void;
  onMemoryHover?: (memory: MemoryData | null) => void;
  className?: string;
  showLegend?: boolean;
  showControls?: boolean;
  similarityThreshold?: number;
  activeGroup?: string | null;
  onGroupsChange?: (groups: Record<string, number>) => void;
}

export interface LegendProps {
  stats: GraphStats;
  isExpanded?: boolean;
  onToggle?: () => void;
  isLoading?: boolean;
}

export interface GraphCanvasProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  panX: number;
  panY: number;
  zoom: number;
  width: number;
  height: number;
  onNodeHover: (nodeId: string | null) => void;
  onNodeClick: (nodeId: string) => void;
  onNodeDragStart: (nodeId: string, e: React.MouseEvent) => void;
  onNodeDragMove: (e: React.MouseEvent) => void;
  onNodeDragEnd: () => void;
  onPanStart: (e: React.MouseEvent) => void;
  onPanMove: (e: React.MouseEvent) => void;
  onPanEnd: () => void;
  onWheel: (e: React.WheelEvent) => void;
  draggingNodeId: string | null;
  selectedNodeId?: string | null;
  highlightNodeIds?: string[];
}

export interface NavigationControlsProps {
  onZoomIn: () => void;
  onZoomOut: () => void;
  onFitToView: () => void;
  onResetView: () => void;
  zoom: number;
  minZoom?: number;
  maxZoom?: number;
}
