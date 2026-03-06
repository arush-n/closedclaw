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
 * Auto-pauses when simulation settles to save CPU.
 * Scales charge strength for large graphs.
 */
export function useForceSimulation(
  nodes: GraphNode[],
  edges: GraphEdge[],
  onTick: () => void,
  enabled = true
): ForceSimulationControls {
  const simulationRef = useRef<d3.Simulation<GraphNode, GraphEdge> | null>(null);
  const lastTickTimeRef = useRef(0);
  // Aggressive throttling for large graphs to save CPU
  const tickThrottleMs = nodes.length > 200 ? 100 : nodes.length > 100 ? 66 : 33;

  useEffect(() => {
    if (!enabled || nodes.length === 0) {
      return;
    }

    // Scale charge strength down for large graphs to avoid O(n^2) blowup
    const scaledCharge =
      nodes.length > 150
        ? FORCE_CONFIG.chargeStrength * 0.4
        : nodes.length > 80
        ? FORCE_CONFIG.chargeStrength * 0.6
        : FORCE_CONFIG.chargeStrength;

    // Faster decay for large graphs so simulation settles sooner
    const scaledAlphaDecay =
      nodes.length > 100
        ? FORCE_CONFIG.alphaDecay * 1.5
        : FORCE_CONFIG.alphaDecay;

    if (!simulationRef.current) {
      const simulation = d3
        .forceSimulation<GraphNode>(nodes)
        .alphaDecay(scaledAlphaDecay)
        .alphaMin(FORCE_CONFIG.alphaMin)
        .velocityDecay(FORCE_CONFIG.velocityDecay)
        .on("tick", () => {
          const now = performance.now();
          if (now - lastTickTimeRef.current >= tickThrottleMs) {
            lastTickTimeRef.current = now;
            onTick();
          }
        })
        .on("end", () => {
          // Final tick when simulation fully settles
          onTick();
        });

      // Link force
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

      // Charge force — scaled for graph size
      simulation.force(
        "charge",
        d3.forceManyBody<GraphNode>().strength(scaledCharge)
      );

      // Collision force
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
          .iterations(nodes.length > 100 ? 1 : 2) // Fewer iterations for big graphs
      );

      // Centering forces
      simulation.force("x", d3.forceX().strength(0.03));
      simulation.force("y", d3.forceY().strength(0.03));

      simulationRef.current = simulation;
    } else {
      // Update existing simulation
      simulationRef.current.nodes(nodes);

      // Update charge for new node count
      const chargeForce = simulationRef.current.force("charge") as d3.ForceManyBody<GraphNode>;
      if (chargeForce) {
        chargeForce.strength(scaledCharge);
      }

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
  }, [nodes, edges, enabled, onTick, tickThrottleMs]);

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
