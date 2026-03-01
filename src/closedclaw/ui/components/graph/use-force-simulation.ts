"use client";

import { useEffect, useRef, useCallback } from "react";
import * as d3 from "d3-force";
import { FORCE_CONFIG } from "./constants";
import type { GraphNode, GraphEdge } from "./types";

export interface ForceSimulationControls {
  simulation: d3.Simulation<GraphNode, GraphEdge> | null;
  reheat: () => void;
  coolDown: () => void;
  isActive: () => boolean;
  stop: () => void;
  getAlpha: () => number;
}

/**
 * Custom hook to manage d3-force simulation lifecycle.
 * Simulation runs during interactions for physics-based node positioning.
 */
export function useForceSimulation(
  nodes: GraphNode[],
  edges: GraphEdge[],
  onTick: () => void,
  enabled = true
): ForceSimulationControls {
  const simulationRef = useRef<d3.Simulation<GraphNode, GraphEdge> | null>(null);
  const lastTickTimeRef = useRef(0);

  useEffect(() => {
    if (!enabled || nodes.length === 0) {
      return;
    }

    // Only create simulation once
    if (!simulationRef.current) {
      const simulation = d3
        .forceSimulation<GraphNode>(nodes)
        .alphaDecay(FORCE_CONFIG.alphaDecay)
        .alphaMin(FORCE_CONFIG.alphaMin)
        .velocityDecay(FORCE_CONFIG.velocityDecay)
        .on("tick", () => {
          const now = performance.now();
          if (now - lastTickTimeRef.current >= 33) {
            lastTickTimeRef.current = now;
            onTick();
          }
        });

      // Link force - spring connections between nodes
      simulation.force(
        "link",
        d3
          .forceLink<GraphNode, GraphEdge>(edges)
          .id((d) => d.id)
          .distance(FORCE_CONFIG.linkDistance)
          .strength((link) => {
            if (link.edgeType === "memory-user") {
              return FORCE_CONFIG.linkStrength.memoryUser;
            }
            if (link.edgeType === "similarity") {
              return link.similarity * FORCE_CONFIG.linkStrength.similarity;
            }
            return FORCE_CONFIG.linkStrength.memoryMemory;
          })
      );

      // Charge force - repulsion between nodes
      simulation.force(
        "charge",
        d3.forceManyBody<GraphNode>().strength(FORCE_CONFIG.chargeStrength)
      );

      // Collision force - prevent node overlap
      simulation.force(
        "collide",
        d3
          .forceCollide<GraphNode>()
          .radius((d) =>
            d.type === "user"
              ? FORCE_CONFIG.collisionRadius.user
              : FORCE_CONFIG.collisionRadius.memory
          )
          .strength(0.7)
      );

      // Centering forces
      simulation.force("x", d3.forceX().strength(0.03));
      simulation.force("y", d3.forceY().strength(0.03));

      simulationRef.current = simulation;
    } else {
      // Update nodes and edges
      simulationRef.current.nodes(nodes);
      const linkForce = simulationRef.current.force("link") as d3.ForceLink<
        GraphNode,
        GraphEdge
      >;
      if (linkForce) {
        linkForce.links(edges);
      }
      simulationRef.current.alpha(0.3).restart();
    }

    return () => {
      if (simulationRef.current) {
        simulationRef.current.stop();
      }
    };
  }, [nodes, edges, enabled, onTick]);

  const reheat = useCallback(() => {
    if (simulationRef.current) {
      simulationRef.current.alpha(FORCE_CONFIG.alphaTarget).restart();
    }
  }, []);

  const coolDown = useCallback(() => {
    if (simulationRef.current) {
      simulationRef.current.alphaTarget(0);
    }
  }, []);

  const isActive = useCallback(() => {
    if (simulationRef.current) {
      return simulationRef.current.alpha() > FORCE_CONFIG.alphaMin;
    }
    return false;
  }, []);

  const stop = useCallback(() => {
    if (simulationRef.current) {
      simulationRef.current.stop();
    }
  }, []);

  const getAlpha = useCallback(() => {
    if (simulationRef.current) {
      return simulationRef.current.alpha();
    }
    return 0;
  }, []);

  return {
    simulation: simulationRef.current,
    reheat,
    coolDown,
    isActive,
    stop,
    getAlpha,
  };
}
