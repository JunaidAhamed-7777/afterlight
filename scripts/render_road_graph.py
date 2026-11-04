"""Render the README road graph from the canonical city and recorded route.

Run from any directory: python scripts/render_road_graph.py
Uses only the standard library; does not change the map or run a simulation.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
from pathlib import Path
import sys
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sim.network import shortest_route


NAVY, MUTED, LINE = "#0A1F44", "#52627A", "#A2B1C5"
TEAL, AMBER, PAPER = "#147D73", "#A36812", "#F8FAFC"
NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", NS)


def element(parent: ET.Element, tag: str, **attrs: object) -> ET.Element:
    return ET.SubElement(parent, f"{{{NS}}}{tag}", {
        key.replace("_", "-"): str(value) for key, value in attrs.items()
    })


def label(parent: ET.Element, x: float, y: float, value: str,
          size: int = 22, color: str = NAVY, **attrs: object) -> None:
    element(parent, "text", x=x, y=y, fill=color, font_size=size, **attrs).text = value


def line(parent: ET.Element, x1: float, y1: float, x2: float, y2: float,
         color: str = LINE, width: float = 2, **attrs: object) -> None:
    element(parent, "line", x1=x1, y1=y1, x2=x2, y2=y2,
            stroke=color, stroke_width=width, **attrs)


def path(parent: ET.Element, points: list[tuple[float, float]],
         color: str, width: float, **attrs: object) -> None:
    data = "M " + " L ".join(f"{x:.2f},{y:.2f}" for x, y in points)
    element(parent, "path", d=data, fill="none", stroke=color,
            stroke_width=width, stroke_linecap="round", stroke_linejoin="round", **attrs)


def render() -> Path:
    source = ROOT / "assets/map/city_manifest.json"
    graph = json.loads(source.read_text(encoding="utf-8"))
    nodes = {n["id"]: n for n in graph["nodes"]}
    edges = {e["id"]: e for e in graph["edges"]}
    catalog = json.loads((ROOT / "web/public/replays/catalog.json").read_text(encoding="utf-8"))
    recording = next(r for r in catalog["runs"] if r["title"] == "Cross-city response")
    pickup = next(p for p in graph["pickups"] if p["id"] == recording["pickup_id"])
    hospital = next(h for h in graph["hospitals"] if h["id"] == recording["hospital_id"])
    route = shortest_route(graph, pickup["edge_id"], hospital["destination_node"])
    with gzip.open(ROOT / "web/public/replays" / recording["url"], "rt", encoding="utf-8") as saved:
        if json.load(saved)["scenario"]["route_edges"] != route:
            raise ValueError("Recorded route differs from the canonical shortest route")

    svg = ET.Element(f"{{{NS}}}svg", {
        "width": "1500", "height": "1100", "viewBox": "0 0 1500 1100",
        "role": "img", "aria-labelledby": "graph-title graph-description",
    })
    element(svg, "title", id="graph-title").text = "AFTERLIGHT: the city as a directed road graph"
    element(svg, "desc", id="graph-description").text = (
        f"Actual canonical layout: {len(nodes)} nodes, {len(graph['roads'])} physical roads, "
        f"{len(edges)} directed edges and {len(graph['connections']):,} permitted edge transitions. "
        f"The {len(route)}-edge recorded Cross-city route runs from curb pickup {pickup['id']} to "
        f"{hospital['name']}. Both hospitals and all graph nodes are shown. Opposing edges overlap "
        "in the city overview; an enlarged H00 corridor shows its four nodes, three segments and "
        "six directed edges. Pickup anchors attach to edges; they are not graph nodes. "
        "Dijkstra minimizes edge length while following permitted turns."
    )
    element(svg, "metadata").text = json.dumps({
        "source": str(source.relative_to(ROOT)).replace("\\", "/"),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "recording_id": recording["id"], "route_edges": route,
        "generator": "scripts/render_road_graph.py",
    }, sort_keys=True)
    element(svg, "style").text = (
        'text { font-family: Inter, "Segoe UI", system-ui, sans-serif; } '
        '.node-label { paint-order: stroke; stroke: #F8FAFC; stroke-width: 6px; stroke-linejoin: round; }'
    )
    defs = element(svg, "defs")
    for name, color in (("edge-arrow", NAVY), ("route-arrow", TEAL)):
        marker = element(defs, "marker", id=name, viewBox="0 0 10 10", refX=8, refY=5,
                         markerWidth=6, markerHeight=6, orient="auto", markerUnits="userSpaceOnUse")
        element(marker, "path", d="M 0 0 L 10 5 L 0 10 Z", fill=color)
    element(svg, "rect", width=1500, height=1100, rx=12, fill=PAPER)
    label(svg, 60, 66, "The city is a directed graph", 42, font_weight=700)
    label(svg, 60, 108, "Actual road topology, with the recorded Cross-city route highlighted", 24, MUTED)
    label(svg, 60, 163,
          f"{len(nodes)} nodes  ·  {len(graph['roads'])} physical roads  ·  "
          f"{len(edges)} directed edges  ·  {len(graph['connections']):,} permitted transitions", 25, font_weight=600)
    line(svg, 60, 192, 1440, 192, "#D9E2EC", 1)
    line(svg, 922, 225, 922, 975, "#D9E2EC", 1)

    # Preserve canonical XY positions, flipping Y only for SVG's downward axis.
    xs, ys = ([n["position"][axis] for n in nodes.values()] for axis in (0, 1))
    span = max(max(xs) - min(xs), max(ys) - min(ys))
    scale = 710 / span
    center_x, center_y = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2

    def xy(point: list[float]) -> tuple[float, float]:
        return 477 + (point[0] - center_x) * scale, 591 - (point[1] - center_y) * scale

    network = element(svg, "g", id="canonical-network")
    # Show every split segment once; its reverse has the same centerline.
    seen = set()
    for edge in edges.values():
        pair = tuple(sorted((edge["from_node"], edge["to_node"])))
        if pair in seen:
            continue
        seen.add(pair)
        segment = element(network, "g", data_segment="|".join(pair))
        element(segment, "title").text = " ↔ ".join(pair)
        path(segment, [xy(p) for p in edge["centerline"]], LINE, 2.3)

    selected = element(svg, "g", id="selected-route")
    for index, edge_id in enumerate(route):
        edge = edges[edge_id]
        points = [xy(p) for p in edge["centerline"]]
        if index == 0:
            # Begin at the curb anchor's centerline projection, not the edge origin.
            a, b = points
            p = xy(pickup["position"])
            dx, dy = b[0] - a[0], b[1] - a[1]
            t = max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)))
            points[0] = (a[0] + t * dx, a[1] + t * dy)
        segment = element(selected, "g", data_edge=edge_id)
        element(segment, "title").text = f"{edge_id}: {edge['from_node']} → {edge['to_node']}"
        path(segment, points, TEAL, 5)
        a, b = points[0], points[-1]
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        if length > 18:
            # Separate arrowhead so direction stays legible without covering nodes.
            mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
            ux, uy = dx / length, dy / length
            tip = (mx + 5 * ux, my + 5 * uy)
            path(segment, [(mx - 4 * ux + 4 * uy, my - 4 * uy - 4 * ux), tip,
                           (mx - 4 * ux - 4 * uy, my - 4 * uy + 4 * ux)], TEAL, 2.5)

    node_group = element(svg, "g", id="graph-nodes")
    for node in nodes.values():
        x, y = xy(node["position"])
        primary = node["kind"] == "primary_intersection"
        dot = element(node_group, "circle", cx=f"{x:.2f}", cy=f"{y:.2f}",
                      r=4.5 if primary else 2.8, fill=NAVY,
                      stroke=AMBER if node["signalized"] else PAPER,
                      stroke_width=1.6 if node["signalized"] else 0.7, data_node=node["id"])
        element(dot, "title").text = node["id"] + (" · signalized" if node["signalized"] else "")

    for h in graph["hospitals"]:
        x, y = xy(nodes[h["destination_node"]]["position"])
        element(svg, "rect", x=x-10, y=y-10, width=20, height=20, rx=3, fill=TEAL, stroke=PAPER, stroke_width=2)
        label(svg, x, y+5, "H", 14, "#FFFFFF", text_anchor="middle", font_weight=700)
        label(svg, x, y-23, h["name"], 22, TEAL, text_anchor="middle", font_weight=600, **{"class": "node-label"})
    px, py = xy(pickup["position"])
    element(svg, "circle", cx=px, cy=py, r=8, fill=PAPER, stroke=TEAL, stroke_width=3)
    line(svg, px, py+10, px+25, py+25, TEAL, 1.5)
    label(svg, px+32, py+30, f"{pickup['id']} · curb pickup", 22, TEAL, **{"class": "node-label"})
    label(svg, 60, 996, "Paired edges overlap in this overview; directions appear in the close-up.", 21, MUTED)

    # An actual split corridor, enlarged to explain graph semantics.
    road_id = "H00"
    road = next(r for r in graph["roads"] if r["id"] == road_id)
    forward = [e for e in graph["edges"] if e["road_id"] == road_id and e["id"].endswith("_F")]
    forward.sort(key=lambda e: math.dist(nodes[road["from_node"]]["position"], e["centerline"][0]))
    if len(forward) != 3:
        raise ValueError("H00 changed; revise the close-up layout before regenerating")
    length = sum(e["length_m"] for e in forward)
    ids = [forward[0]["from_node"], *[e["to_node"] for e in forward]]
    positions = [980.0]
    for edge in forward:
        positions.append(positions[-1] + 440 * edge["length_m"] / length)
    label(svg, 965, 254, "From road surface to graph", 28, font_weight=700)
    label(svg, 965, 291, f"One two-way corridor: {road_id} · {length:g} m", 22, MUTED)
    line(svg, positions[0], 338, positions[-1], 338, LINE, 12, stroke_linecap="round")
    label(svg, positions[0], 321, ids[0], 20)
    label(svg, positions[-1], 321, ids[-1], 20, text_anchor="end")
    label(svg, 965, 393, "Split at access nodes; add both directions", 22)
    for i, edge in enumerate(forward):
        a, b = positions[i], positions[i+1]
        line(svg, a+10, 430, b-10, 430, NAVY, 2, marker_end="url(#edge-arrow)")
        line(svg, b-10, 450, a+10, 450, NAVY, 2, marker_end="url(#edge-arrow)")
        label(svg, (a+b)/2, 518, f"{edge['length_m']:g} m", 20, MUTED, text_anchor="middle")
    for x, node_id in zip(positions, ids):
        element(svg, "circle", cx=x, cy=440, r=6, fill=NAVY)
        label(svg, x, 486, node_id, 20, text_anchor="middle")
    label(svg, 965, 565, "4 nodes · 3 segments · 6 directed edges", 23, font_weight=600)
    label(svg, 965, 601, "Arrows represent edges, not individual lanes.", 21, MUTED)
    line(svg, 965, 634, 1440, 634, "#D9E2EC", 1)
    label(svg, 965, 686, "How routing uses the graph", 28, font_weight=700)
    label(svg, 965, 729, "Nodes: junctions, access points, destinations", 21)
    label(svg, 965, 765, "Edges: direction, length and permissions", 21)
    label(svg, 965, 801, "Connections: permitted turns between edges", 21)
    label(svg, 965, 855, "Dijkstra minimizes total edge length", 23, font_weight=600)
    label(svg, 965, 890, "while following those legal connections.", 22, MUTED)
    label(svg, 965, 950, f"Highlighted: {recording['title']}", 23, TEAL, font_weight=600)
    label(svg, 965, 984, f"{pickup['id']} → {hospital['name']} · {len(route)} edges", 21, TEAL)

    line(svg, 60, 1022, 1440, 1022, "#D9E2EC", 1)
    for x, title, radius, stroke in ((72, "Signalized junction", 5, AMBER), (380, "Other graph node", 3.5, NAVY)):
        element(svg, "circle", cx=x, cy=1060, r=radius, fill=NAVY, stroke=stroke, stroke_width=2)
        label(svg, x+18, 1067, title, 21, MUTED)
    line(svg, 671, 1060, 712, 1060, TEAL, 5)
    label(svg, 725, 1067, "Recorded route", 21, MUTED)
    label(svg, 1440, 1067, "Source: canonical city manifest + saved replay", 19, MUTED, text_anchor="end")
    ET.indent(svg)
    output = ROOT / "docs/images/road-graph.svg"
    ET.ElementTree(svg).write(output, encoding="utf-8", xml_declaration=True)
    return output


if __name__ == "__main__":
    print(render())
