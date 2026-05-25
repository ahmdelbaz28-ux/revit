import numpy as np
from typing import List, Dict, Tuple
from math import sqrt, exp


class NumericalDiscretizer:
    def __init__(self, resolution: float = 1.0):
        self.resolution = resolution

    def discretize_state(self, topology) -> Dict:
        if not topology.nodes:
            return {"grid_size": 0, "state_matrix": np.array([]), "node_map": {}}

        positions = [(n.x, n.y) for n in topology.nodes if hasattr(n, 'x') and hasattr(n, 'y')]
        if not positions:
            positions = [(0.0, 0.0)]

        xs = [p[0] for p in positions]
        ys = [p[1] for p in positions]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        width = max(max_x - min_x, 1.0)
        height = max(max_y - min_y, 1.0)

        cols = max(1, int(width / self.resolution) + 2)
        rows = max(1, int(height / self.resolution) + 2)

        state_matrix = np.zeros((rows, cols))
        node_map = {}

        for i, node in enumerate(topology.nodes):
            if hasattr(node, 'x') and hasattr(node, 'y'):
                col = int((node.x - min_x) / self.resolution)
                row = int((node.y - min_y) / self.resolution)
                col = max(0, min(cols - 1, col))
                row = max(0, min(rows - 1, row))
                node_map[node.node_id] = (row, col)

                if node.status == "failed":
                    state_matrix[row, col] = 1.0
                elif node.status == "operational":
                    state_matrix[row, col] = 0.0
                else:
                    prob = getattr(node, 'failure_probability', 0.0)
                    state_matrix[row, col] = prob

        return {
            "grid_size": self.resolution,
            "rows": rows,
            "cols": cols,
            "state_matrix": state_matrix,
            "node_map": node_map,
            "origin": (min_x, min_y),
            "width": width,
            "height": height
        }

    def apply_kernel(self, state_dict: Dict, kernel_type: str, kernel_params: Dict = None) -> np.ndarray:
        if state_dict["state_matrix"].size == 0:
            return np.array([])

        state = state_dict["state_matrix"].copy()
        rows, cols = state.shape
        result = np.zeros_like(state)

        if kernel_type == "smoke":
            sigma = kernel_params.get("sigma", 2.0) if kernel_params else 2.0
            kernel_size = int(sigma * 3)
            kernel = np.zeros((2 * kernel_size + 1, 2 * kernel_size + 1))
            for i in range(-kernel_size, kernel_size + 1):
                for j in range(-kernel_size, kernel_size + 1):
                    kernel[i + kernel_size, j + kernel_size] = exp(-(i**2 + j**2) / (2 * sigma**2))
            kernel = kernel / kernel.sum()

            from scipy.signal import convolve2d
            result = convolve2d(state, kernel, mode='same', boundary='symm')

        elif kernel_type == "electrical":
            result = state.copy()
            for i in range(rows):
                for j in range(cols):
                    if state[i, j] > 0:
                        for di in [-1, 0, 1]:
                            for dj in [-1, 0, 1]:
                                ni, nj = i + di, j + dj
                                if 0 <= ni < rows and 0 <= nj < cols:
                                    dist = sqrt(di**2 + dj**2)
                                    if dist > 0:
                                        result[ni, nj] = max(result[ni, nj], state[i, j] * 0.7 / dist)

        elif kernel_type == "fire":
            threshold = kernel_params.get("threshold", 0.3) if kernel_params else 0.3
            result = state.copy()
            for i in range(rows):
                for j in range(cols):
                    if state[i, j] > threshold:
                        for di in [-1, 0, 1]:
                            for dj in [-1, 0, 1]:
                                if di == 0 and dj == 0:
                                    continue
                                ni, nj = i + di, j + dj
                                if 0 <= ni < rows and 0 <= nj < cols:
                                    result[ni, nj] = min(1.0, result[ni, nj] + state[i, j] * 0.4)

        elif kernel_type == "structural":
            result = state.copy()
            for i in range(rows):
                for j in range(cols):
                    if state[i, j] > 0.5:
                        for di in [-2, -1, 0, 1, 2]:
                            for dj in [-2, -1, 0, 1, 2]:
                                ni, nj = i + di, j + dj
                                if 0 <= ni < rows and 0 <= nj < cols:
                                    dist = max(sqrt(di**2 + dj**2), 0.1)
                                    result[ni, nj] = min(1.0, result[ni, nj] + state[i, j] * 0.2 / dist)

        return result

    def reconstruct_tensor(self, discretized: Dict, topology) -> Dict:
        state_matrix = discretized["state_matrix"]
        if state_matrix.size == 0:
            return {"max_risk": 0.0, "avg_risk": 0.0, "spatial_distribution": []}

        max_risk = float(state_matrix.max())
        avg_risk = float(state_matrix.mean())
        rows, cols = state_matrix.shape
        origin = discretized["origin"]
        resolution = discretized["grid_size"]

        spatial_dist = []
        for i in range(rows):
            for j in range(cols):
                if state_matrix[i, j] > 0.01:
                    spatial_dist.append({
                        "x": round(origin[0] + j * resolution, 2),
                        "y": round(origin[1] + i * resolution, 2),
                        "risk": round(float(state_matrix[i, j]), 4)
                    })

        return {
            "max_risk": max_risk,
            "avg_risk": avg_risk,
            "spatial_distribution": spatial_dist
        }