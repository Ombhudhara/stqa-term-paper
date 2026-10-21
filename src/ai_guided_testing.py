"""Coverage- and novelty-guided genetic search for _match_one inputs."""

import random
import time
from dataclasses import replace

from .random_testing import (
    NUMERIC_KEYS,
    NUMERIC_OPERATORS,
    NUMERIC_VALUES,
    STRING_KEYS,
    STRING_OPERATORS,
    STRING_VALUES,
    UNARY_KEYS,
    UNARY_VALUES,
    Candidate,
    InputDomain,
    canonical_json,
)


class GeneticInputGenerator(object):
    """Ask/tell genetic search; each candidate is evaluated exactly once."""

    def __init__(self, seed, population_size=10, mutation_rate=0.8):
        if population_size < 2:
            raise ValueError("population_size must be at least 2")
        if not 0.0 <= mutation_rate <= 1.0:
            raise ValueError("mutation_rate must be between 0 and 1")
        self.random = random.Random(seed)
        self.domain = InputDomain(seed ^ 0x5A17)
        self.population_size = population_size
        self.mutation_rate = mutation_rate
        self.seen_candidates = set()
        self.seen_lines = set()
        self.seen_arcs = set()
        self.seen_behaviors = set()
        self.population = []
        self.generation_candidates = []
        self.generation_queue = []
        self.generation = 0
        self.pending = None
        self.progress = []

    def _unique_sample(self):
        for _attempt in range(2000):
            candidate = self.domain.sample()
            identifier = candidate.identifier()
            if identifier not in self.seen_candidates:
                self.seen_candidates.add(identifier)
                return candidate
        raise RuntimeError("No unique candidate remains in the configured domain")

    def _tournament_parent(self):
        contestants = self.random.sample(
            self.population,
            min(3, len(self.population)),
        )
        return max(contestants, key=lambda item: item["fitness"])["candidate"]

    def _crossover(self, first, second):
        if first.kind != second.kind:
            return self.random.choice((first, second))
        if first.kind == "unary":
            return Candidate(
                kind="unary",
                key=self.random.choice((first.key, second.key)),
                value=self.random.choice((first.value, second.value)),
                missing=self.random.choice((first.missing, second.missing)),
                negated=self.random.choice((first.negated, second.negated)),
            )
        return Candidate(
            kind=first.kind,
            key=self.random.choice((first.key, second.key)),
            value=self.random.choice((first.value, second.value)),
            operator=self.random.choice((first.operator, second.operator)),
            operand=self.random.choice((first.operand, second.operand)),
        )

    def _mutate(self, candidate):
        if self.random.random() >= self.mutation_rate:
            return candidate
        if candidate.kind == "unary":
            field = self.random.choice(("key", "value", "missing", "negated"))
            if field == "key":
                return replace(candidate, key=self.random.choice(UNARY_KEYS))
            if field == "value":
                return replace(candidate, value=self.random.choice(UNARY_VALUES))
            if field == "missing":
                return replace(candidate, missing=not candidate.missing)
            return replace(candidate, negated=not candidate.negated)
        if candidate.kind == "numeric":
            field = self.random.choice(("key", "value", "operator", "operand"))
            choices = {
                "key": NUMERIC_KEYS,
                "value": NUMERIC_VALUES,
                "operator": NUMERIC_OPERATORS,
                "operand": NUMERIC_VALUES,
            }
        else:
            field = self.random.choice(("key", "value", "operator", "operand"))
            choices = {
                "key": STRING_KEYS,
                "value": STRING_VALUES,
                "operator": STRING_OPERATORS,
                "operand": STRING_VALUES,
            }
        return replace(candidate, **{field: self.random.choice(choices[field])})

    def _prepare_next_generation(self):
        if self.generation_candidates:
            self.population = sorted(
                self.generation_candidates,
                key=lambda item: item["fitness"],
                reverse=True,
            )
            self.generation_candidates = []
        if not self.population:
            self.generation_queue = [
                self._unique_sample() for _ in range(self.population_size)
            ]
            self.generation = 0
            return

        self.generation += 1
        next_candidates = []
        attempts = 0
        max_attempts = self.population_size * 100
        while len(next_candidates) < self.population_size and attempts < max_attempts:
            attempts += 1
            parent_a = self._tournament_parent()
            parent_b = self._tournament_parent()
            child = self._mutate(self._crossover(parent_a, parent_b))
            identifier = child.identifier()
            if identifier in self.seen_candidates:
                continue
            self.seen_candidates.add(identifier)
            next_candidates.append(child)
        while len(next_candidates) < self.population_size:
            next_candidates.append(self._unique_sample())
        self.generation_queue = next_candidates

    def next_candidate(self):
        if self.pending is not None:
            raise RuntimeError("Call observe() before requesting another candidate")
        if not self.generation_queue:
            self._prepare_next_generation()
        if not self.generation_queue:
            raise RuntimeError("Genetic search could not prepare a candidate")
        self.pending = self.generation_queue.pop(0)
        return self.pending

    def observe(self, buggy_observation):
        """Update fitness from buggy-only feedback; fixed output is never supplied."""
        if self.pending is None:
            raise RuntimeError("No candidate is awaiting an observation")

        lines = set(buggy_observation.get("coverage_lines", []))
        arcs = set(
            tuple(arc) for arc in buggy_observation.get("coverage_arcs", [])
        )
        behavior = canonical_json({
            "ok": buggy_observation.get("ok"),
            "result": buggy_observation.get("result"),
            "exception": buggy_observation.get("exception"),
            "message": buggy_observation.get("message"),
        })
        new_lines = lines - self.seen_lines
        new_arcs = arcs - self.seen_arcs
        new_behavior = behavior not in self.seen_behaviors

        # Fitness = 10*new arcs + 2*new lines + 3*new buggy outcomes.
        # The fixed implementation is deliberately absent from this objective.
        fitness = 10 * len(new_arcs) + 2 * len(new_lines) + 3 * int(new_behavior)
        self.seen_lines.update(lines)
        self.seen_arcs.update(arcs)
        self.seen_behaviors.add(behavior)
        record = {
            "candidate": self.pending,
            "fitness": fitness,
            "new_lines": len(new_lines),
            "new_arcs": len(new_arcs),
            "new_behavior": int(new_behavior),
            "generation": self.generation,
        }
        self.generation_candidates.append(record)
        self.progress.append({
            "generation": self.generation,
            "fitness": fitness,
            "new_lines": len(new_lines),
            "new_arcs": len(new_arcs),
            "new_behavior": int(new_behavior),
            "unique_lines": len(self.seen_lines),
            "unique_arcs": len(self.seen_arcs),
            "unique_behaviors": len(self.seen_behaviors),
        })
        self.pending = None
        return record

    def next_candidate_with_overhead(self):
        started = time.perf_counter()
        candidate = self.next_candidate()
        return candidate, time.perf_counter() - started

    def observe_with_overhead(self, buggy_observation):
        started = time.perf_counter()
        record = self.observe(buggy_observation)
        return record, time.perf_counter() - started