// Colors for graph visualization
export const colors = {
  background: {
    primary: "#030712",
    secondary: "#081120",
    accent: "#0b1630",
  },
  memory: {
    primary: "rgba(244, 246, 255, 0.24)",
    secondary: "rgba(244, 246, 255, 0.36)",
    accent: "rgba(210, 220, 255, 0.44)",
    border: "rgba(214, 223, 255, 0.72)",
    glow: "rgba(162, 184, 255, 0.55)",
  },
  document: {
    primary: "rgba(255, 255, 255, 0.21)",
    secondary: "rgba(255, 255, 255, 0.31)",
    accent: "rgba(255, 255, 255, 0.31)",
    border: "rgba(255, 255, 255, 0.6)",
    glow: "rgba(147, 197, 253, 0.4)",
  },
  user: {
    primary: "rgba(16, 185, 129, 0.28)",
    secondary: "rgba(52, 211, 153, 0.38)",
    accent: "rgba(94, 234, 212, 0.45)",
    border: "rgba(52, 211, 153, 0.7)",
    glow: "rgba(45, 212, 191, 0.6)",
  },
  connection: {
    weak: "rgba(148, 163, 184, 0.18)",
    medium: "rgba(99, 102, 241, 0.36)",
    strong: "rgba(129, 140, 248, 0.62)",
    similarity: "rgba(203, 213, 225, 0.24)",
  },
  text: {
    primary: "#ffffff",
    secondary: "#e2e8f0",
    muted: "#94a3b8",
  },
  status: {
    new: "rgba(16, 185, 129, 0.5)",
    recent: "rgba(234, 179, 8, 0.62)",
    old: "rgba(100, 116, 139, 0.4)",
  },
  categories: {
    work: "rgba(59, 130, 246, 0.6)",
    personal: "rgba(236, 72, 153, 0.6)",
    knowledge: "rgba(168, 85, 247, 0.6)",
    preference: "rgba(251, 146, 60, 0.6)",
    relationship: "rgba(16, 185, 129, 0.6)",
    default: "rgba(147, 196, 253, 0.6)",
  },
};

// Layout constants
export const LAYOUT_CONSTANTS = {
  centerX: 0,
  centerY: 0,
  nodeSpacing: 200,
  clusterRadius: 300,
  userRadius: 500,
};

// Similarity calculation configuration
export const SIMILARITY_CONFIG = {
  threshold: 0.6, // Minimum similarity to create edge
  maxComparisonsPerNode: 8,
};

// D3-Force simulation configuration — tuned for smooth, fast settling
export const FORCE_CONFIG = {
  linkStrength: {
    similarity: 0.25,
    memoryUser: 0.4,
    memoryMemory: 0.15,
  },
  linkDistance: 200,
  chargeStrength: -500,
  collisionRadius: {
    memory: 40,
    user: 55,
  },
  alphaDecay: 0.05,
  alphaMin: 0.002,
  velocityDecay: 0.7,
  alphaTarget: 0.25,
};

// Graph view settings
export const GRAPH_SETTINGS = {
  initialZoom: 0.6,
  minZoom: 0.1,
  maxZoom: 3,
  zoomStep: 0.2,
  panSpeed: 1,
};

// Animation settings
export const ANIMATION = {
  dimDuration: 300,
  hoverTransition: 150,
  pulseSpeed: 2000,
};

// Node sizes
export const NODE_SIZES = {
  memory: {
    default: 4,
    hovered: 7,
    selected: 8,
  },
  user: {
    default: 8,
    hovered: 11,
    selected: 13,
  },
};

// Get color for a memory based on category
export function getMemoryColor(categories?: string[]): string {
  if (!categories || categories.length === 0) {
    return colors.categories.default;
  }
  
  const category = categories[0].toLowerCase();
  if (category.includes("work") || category.includes("project")) {
    return colors.categories.work;
  }
  if (category.includes("personal") || category.includes("life")) {
    return colors.categories.personal;
  }
  if (category.includes("knowledge") || category.includes("learn")) {
    return colors.categories.knowledge;
  }
  if (category.includes("preference") || category.includes("like")) {
    return colors.categories.preference;
  }
  if (category.includes("relationship") || category.includes("person")) {
    return colors.categories.relationship;
  }
  
  return colors.categories.default;
}

// Get age-based opacity for memory nodes
export function getMemoryAgeOpacity(createdAt?: string): number {
  if (!createdAt) return 0.8;
  
  const now = Date.now();
  const created = new Date(createdAt).getTime();
  const ageMs = now - created;
  const ageHours = ageMs / (1000 * 60 * 60);
  
  if (ageHours < 24) return 1.0; // New
  if (ageHours < 168) return 0.9; // This week
  if (ageHours < 720) return 0.7; // This month
  return 0.5; // Older
}
