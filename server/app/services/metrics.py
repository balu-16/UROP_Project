from collections import Counter, deque
from statistics import mean
from time import perf_counter


class MetricsService:
    def __init__(self):
        self.request_counts = Counter()
        self.arm_counts = Counter()
        self.latencies = deque(maxlen=1000)
        self.rewards = deque(maxlen=1000)
        self.started_at = perf_counter()

    def record_request(self, name: str) -> None:
        self.request_counts[name] += 1

    def record_chat(self, arm: str, latency_ms: float, reward: float | None) -> None:
        self.arm_counts[arm] += 1
        self.latencies.append(latency_ms)
        if reward is not None:
            self.rewards.append(reward)

    def snapshot(self, vector_index_size: int, graph_stats: dict) -> dict:
        sorted_latencies = sorted(self.latencies)
        def percentile(p: float) -> float:
            if not sorted_latencies:
                return 0.0
            index = min(len(sorted_latencies) - 1, int((len(sorted_latencies) - 1) * p))
            return float(sorted_latencies[index])

        return {
            "uptime_seconds": perf_counter() - self.started_at,
            "request_counts": dict(self.request_counts),
            "arm_distribution": dict(self.arm_counts),
            "latency_ms": {"p50": percentile(0.5), "p95": percentile(0.95)},
            "average_reward": mean(self.rewards) if self.rewards else 0.0,
            "vector_index_size": vector_index_size,
            "graph": graph_stats,
        }

