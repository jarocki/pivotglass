"""STIX relationship graph and visualization.

Builds an in-memory graph from workspace STIX objects and relationships,
renders text-based trees using Rich Tree widget, and exports to GEXF/STIX.

@decision DEC-GRAPH-001
@title In-memory adjacency list with dict[stix_id, GraphNode] + edge list
@status accepted
@rationale STIX graphs in OSINT investigations are typically small (tens to
           hundreds of nodes, not millions). A lightweight adjacency list
           (dict of nodes + list of (src, tgt, type) tuples) is simpler than
           networkx or igraph, avoids a new dependency, and provides O(1) node
           lookup by STIX ID. Cycle safety is achieved via a visited: set
           threaded through the recursive _build_subtree — the standard DFS
           cycle-prevention pattern.

@decision DEC-GRAPH-002
@title Rich Tree widget for tree rendering, plain-text fallback via Console(file=StringIO)
@status accepted
@rationale Rich Tree is already a project dependency (used in console.py). Using it
           here keeps the rendering consistent with the rest of the UI. render_text()
           captures a Rich Console's output into a StringIO so callers without a
           live terminal get a plain-text string. This avoids a separate ASCII art
           rendering pass and keeps the text output visually identical to the Rich
           terminal output.

@decision DEC-GRAPH-003
@title GEXF 1.2 format with gexf/graph/nodes/edges structure
@status accepted
@rationale GEXF is the native import format for Gephi, the dominant free graph
           visualization tool in the CTI community. The 1.2draft namespace is used
           because it is the most widely supported version in Gephi. The export
           uses Python's stdlib xml.etree.ElementTree — no extra dependency needed.

@decision DEC-GRAPH-004
@title export_stix_bundle returns plain dict (not stix2 Bundle object)
@status accepted
@rationale The console can serialize this dict with json.dumps() without needing to
           import stix2. Tests can inspect it with simple dict key access. If a
           python-stix2 Bundle is needed later, wrap with create_bundle() from
           models/stix.py. The dict always has type="bundle" and an "objects" list
           to satisfy consumers expecting STIX 2.1 bundle structure.

@decision DEC-GRAPH-005
@title Unconnected nodes appear at root level under a separate 'Unconnected' branch
@status accepted
@rationale During investigations, many discovered observables are not yet linked
           by explicit relationships. Hiding them from the tree view would make the
           graph misleading. Grouping them under an 'Unconnected' branch at the root
           keeps them visible without cluttering the relationship sub-tree.
"""

from __future__ import annotations

import io
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from rich.console import Console
from rich.tree import Tree


@dataclass
class GraphNode:
    """A node in the STIX relationship graph.

    Parameters
    ----------
    stix_id:
        The STIX 2.1 identifier string (e.g. "ipv4-addr--abc123").
    stix_type:
        The STIX object type (e.g. "ipv4-addr", "domain-name").
    value:
        The observable value (e.g. "1.2.3.4", "evil.com").
    children:
        Direct child GraphNode objects — populated during tree construction,
        not during build_from_workspace(). Not used by RelationshipGraph
        internally (the graph uses an edge list); reserved for external callers
        that want a pre-linked tree structure.
    """

    stix_id: str
    stix_type: str
    value: str
    children: list[GraphNode] = field(default_factory=list)


class RelationshipGraph:
    """In-memory graph of STIX objects and their relationships.

    Build the graph from workspace data, then render or export it in
    several formats. All rendering is side-effect-free — calling render_*
    or export_* does not modify the graph state.

    Usage::

        g = RelationshipGraph()
        g.build_from_workspace(stix_objects, relationships)
        tree = g.render_tree()
        console.print(tree)
    """

    def __init__(self) -> None:
        self._nodes: dict[str, GraphNode] = {}       # stix_id -> node
        self._edges: list[tuple[str, str, str]] = []  # (source, target, rel_type)

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def build_from_workspace(
        self,
        stix_objects: list[dict],
        relationships: list[dict] | None = None,
    ) -> None:
        """Build the graph from workspace data.

        Parameters
        ----------
        stix_objects:
            List of plain dicts as returned by WorkspaceManager.get_stix_objects().
            Each dict must have "id" and "type" keys; "value" is recommended.
        relationships:
            Optional list of relationship dicts. Each must have "source_ref",
            "target_ref", and optionally "relationship_type" (defaults to
            "related-to"). These are the explicit STIX SRO relationships.

        Notes
        -----
        Calling build_from_workspace() on an already-populated graph is safe —
        it appends to (does not replace) the existing nodes and edges. To start
        fresh, construct a new RelationshipGraph instance.
        """
        for obj in stix_objects:
            node = GraphNode(
                stix_id=obj.get("id", ""),
                stix_type=obj.get("type", ""),
                value=obj.get("value", ""),
            )
            if node.stix_id:
                self._nodes[node.stix_id] = node

        if relationships:
            for rel in relationships:
                src = rel.get("source_ref", "")
                tgt = rel.get("target_ref", "")
                rel_type = rel.get("relationship_type", "related-to")
                if src and tgt:
                    self._edges.append((src, tgt, rel_type))

    # ------------------------------------------------------------------
    # Render — Rich Tree
    # ------------------------------------------------------------------

    def render_tree(self, root_id: str | None = None) -> Tree:
        """Render the graph as a Rich Tree starting from a root node.

        Parameters
        ----------
        root_id:
            STIX ID of the node to use as the tree root. If None or not found,
            the first inserted node is used as root. If the graph is empty,
            returns a placeholder tree.

        Returns
        -------
        rich.tree.Tree
            Renderable tree. Pass to a Rich Console with console.print(tree).
        """
        if not self._nodes:
            return Tree("[dim]Empty graph[/dim]")

        # Resolve root node
        if root_id and root_id in self._nodes:
            root = self._nodes[root_id]
        else:
            root = next(iter(self._nodes.values()))

        tree = Tree(f"[bold]{root.stix_type}[/bold]: {root.value}")
        visited: set[str] = set()
        self._build_subtree(tree, root.stix_id, visited)

        # Show unconnected nodes (not visited during DFS) as a separate branch
        # See DEC-GRAPH-005
        unvisited = [n for nid, n in self._nodes.items() if nid not in visited]
        if unvisited:
            orphan_branch = tree.add("[dim]Unconnected[/dim]")
            for node in unvisited:
                orphan_branch.add(f"[bold]{node.stix_type}[/bold]: {node.value}")

        return tree

    def _build_subtree(self, parent: Tree, node_id: str, visited: set[str]) -> None:
        """Recursively add child branches for edges connected to node_id.

        Uses DFS with a visited set to prevent infinite loops on cyclic graphs.
        Traverses edges in both directions (undirected view) so that a domain
        that *targets* an IP shows up as a child of that IP when the IP is root.

        Parameters
        ----------
        parent:
            The Rich Tree branch to attach children to.
        node_id:
            The current node's STIX ID.
        visited:
            Shared mutable set of already-processed node IDs.
        """
        visited.add(node_id)

        for src, tgt, rel_type in self._edges:
            if src == node_id:
                neighbor_id = tgt
            elif tgt == node_id:
                neighbor_id = src
            else:
                continue

            if neighbor_id in visited or neighbor_id not in self._nodes:
                continue

            neighbor = self._nodes[neighbor_id]
            branch = parent.add(
                f"[cyan]{rel_type}[/cyan] → [bold]{neighbor.stix_type}[/bold]: {neighbor.value}"
            )
            self._build_subtree(branch, neighbor_id, visited)

    # ------------------------------------------------------------------
    # Render — plain text
    # ------------------------------------------------------------------

    def render_text(self) -> str:
        """Render the graph as plain text.

        Uses a Rich Console backed by StringIO to produce the same output as
        render_tree() but as a plain string (no ANSI escape codes). Safe to
        use in contexts without a live terminal.

        Returns
        -------
        str
            Multi-line text representation of the graph tree.
        """
        buf = io.StringIO()
        console = Console(file=buf, highlight=False, markup=True, no_color=True)
        tree = self.render_tree()
        console.print(tree)
        return buf.getvalue()

    # ------------------------------------------------------------------
    # Export — GEXF
    # ------------------------------------------------------------------

    def export_gexf(self) -> str:
        """Export the graph as GEXF 1.2 XML for Gephi visualization.

        Returns
        -------
        str
            UTF-8 GEXF XML string. Use ET.fromstring() to verify structure.

        Notes
        -----
        GEXF 1.2draft is used for maximum Gephi compatibility. See DEC-GRAPH-003.
        """
        # Root gexf element
        gexf = ET.Element("gexf", {
            "xmlns": "http://gexf.net/1.2",
            "version": "1.2",
        })
        graph_el = ET.SubElement(gexf, "graph", {
            "defaultedgetype": "directed",
            "mode": "static",
        })

        # Nodes
        nodes_el = ET.SubElement(graph_el, "nodes")
        for stix_id, node in self._nodes.items():
            ET.SubElement(nodes_el, "node", {
                "id": stix_id,
                "label": f"{node.stix_type}: {node.value}",
            })

        # Edges
        edges_el = ET.SubElement(graph_el, "edges")
        for idx, (src, tgt, rel_type) in enumerate(self._edges):
            ET.SubElement(edges_el, "edge", {
                "id": str(idx),
                "source": src,
                "target": tgt,
                "label": rel_type,
            })

        return ET.tostring(gexf, encoding="unicode", xml_declaration=False)

    # ------------------------------------------------------------------
    # Export — STIX bundle
    # ------------------------------------------------------------------

    def export_stix_bundle(self) -> dict[str, Any]:
        """Export the graph as a STIX 2.1 bundle dict.

        Returns a plain dict (not a python-stix2 object) containing all
        graph nodes as STIX objects and all edges as STIX relationship objects.
        See DEC-GRAPH-004.

        Returns
        -------
        dict
            STIX 2.1 bundle with type="bundle", id, and objects list.
        """
        import uuid

        objects: list[dict] = []

        # Nodes as STIX observable/object dicts
        for stix_id, node in self._nodes.items():
            objects.append({
                "type": node.stix_type,
                "id": stix_id,
                "value": node.value,
            })

        # Edges as STIX relationship dicts
        for idx, (src, tgt, rel_type) in enumerate(self._edges):
            objects.append({
                "type": "relationship",
                "id": f"relationship--{uuid.uuid4()}",
                "relationship_type": rel_type,
                "source_ref": src,
                "target_ref": tgt,
            })

        return {
            "type": "bundle",
            "id": f"bundle--{uuid.uuid4()}",
            "objects": objects,
        }

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def get_stats(self) -> dict[str, Any]:
        """Return graph statistics.

        Returns
        -------
        dict
            Keys:
            - "node_count" (int): total number of nodes
            - "edge_count" (int): total number of edges
            - "types" (dict[str, int]): count of nodes per STIX type
        """
        type_counts: dict[str, int] = Counter(
            node.stix_type for node in self._nodes.values()
        )
        return {
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "types": dict(type_counts),
        }

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def node_count(self) -> int:
        """Number of nodes in the graph."""
        return len(self._nodes)

    @property
    def edge_count(self) -> int:
        """Number of edges in the graph."""
        return len(self._edges)
