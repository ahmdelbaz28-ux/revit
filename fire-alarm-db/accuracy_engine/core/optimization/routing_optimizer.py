from math import sqrt

def distance(p1, p2):
    return sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)

def build_device_graph(devices: list) -> dict:
    graph = {}
    
    for i, d in enumerate(devices):
        graph[i] = {"pos": (d["x"], d["y"]), "neighbors": {}}
    
    for i in range(len(devices)):
        for j in range(i + 1, len(devices)):
            dist = distance((devices[i]["x"], devices[i]["y"]), (devices[j]["x"], devices[j]["y"]))
            graph[i]["neighbors"][j] = dist
            graph[j]["neighbors"][i] = dist
    
    return graph

def minimum_spanning_tree_length(devices: list) -> float:
    if len(devices) <= 1:
        return 0.0
    
    if len(devices) == 2:
        return distance((devices[0]["x"], devices[0]["y"]), (devices[1]["x"], devices[1]["y"]))
    
    # Simple Prim's algorithm implementation
    import heapq
    
    n = len(devices)
    in_mst = [False] * n
    min_edge = [float('inf')] * n
    parent = [-1] * n
    
    # Start from node 0
    min_edge[0] = 0
    heap = [(0, 0)]  # (weight, node)
    
    total_length = 0.0
    edges_in_mst = 0
    
    while heap and edges_in_mst < n:
        weight, u = heapq.heappop(heap)
        if in_mst[u]:
            continue
        in_mst[u] = True
        total_length += weight
        edges_in_mst += 1
        
        for v in range(n):
            if not in_mst[v]:
                dist = distance((devices[u]["x"], devices[u]["y"]), (devices[v]["x"], devices[v]["y"]))
                if dist < min_edge[v]:
                    min_edge[v] = dist
                    parent[v] = u
                    heapq.heappush(heap, (dist, v))
    
    return total_length

def estimate_cable_cost(devices: list, cost_per_meter: float = 2.0) -> float:
    length = minimum_spanning_tree_length(devices)
    return length * cost_per_meter