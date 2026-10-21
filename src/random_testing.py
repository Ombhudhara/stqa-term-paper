"""Seeded random generation for the youtube-dl _match_one input domain."""

import hashlib
import json
import random
import time
from dataclasses import dataclass


NUMERIC_OPERATORS = ("<", "<=", ">", ">=", "=", "!=")
STRING_OPERATORS = ("=", "!=")
UNARY_KEYS = ("is_live", "has_drm", "title", "description", "duration")
NUMERIC_KEYS = ("view_count", "duration")
STRING_KEYS = ("title", "description")
UNARY_VALUES = (True, False, None, "", "sample", 0)
NUMERIC_VALUES = (0, 1, 10, 100, 101, 1024)
STRING_VALUES = ("", "a", "b", "sample", "youtube")


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


@dataclass(frozen=True)
class Candidate:
    kind: str
    key: str
    value: object = None
    missing: bool = False
    negated: bool = False
    operator: str = ""
    operand: object = None

    def to_test_input(self):
        if self.kind == "unary":
            filter_part = ("!" if self.negated else "") + self.key
            data = {} if self.missing else {self.key: self.value}
        elif self.kind == "numeric":
            filter_part = "%s %s %s" % (self.key, self.operator, self.operand)
            data = {self.key: self.value}
        elif self.kind == "string":
            if self.operand == "":
                filter_part = "%s %s" % (self.key, self.operator)
            else:
                filter_part = '%s %s "%s"' % (
                    self.key,
                    self.operator,
                    self.operand,
                )
            data = {self.key: self.value}
        else:
            raise ValueError("Unknown candidate kind: %s" % self.kind)
        return {"filter_part": filter_part, "dct": data}

    def identifier(self):
        return hashlib.sha256(
            canonical_json(self.to_test_input()).encode("utf-8")
        ).hexdigest()


class InputDomain(object):
    """Sample syntactically valid filters with common and boundary values."""

    def __init__(self, seed):
        self.random = random.Random(seed)

    def sample(self):
        kind = self.random.choice(("unary", "numeric", "string"))
        if kind == "unary":
            missing = self.random.random() < 0.12
            return Candidate(
                kind="unary",
                key=self.random.choice(UNARY_KEYS),
                value=self.random.choice(UNARY_VALUES),
                missing=missing,
                negated=bool(self.random.getrandbits(1)),
            )
        if kind == "numeric":
            return Candidate(
                kind="numeric",
                key=self.random.choice(NUMERIC_KEYS),
                value=self.random.choice(NUMERIC_VALUES),
                operator=self.random.choice(NUMERIC_OPERATORS),
                operand=self.random.choice(NUMERIC_VALUES),
            )
        return Candidate(
            kind="string",
            key=self.random.choice(STRING_KEYS),
            value=self.random.choice(STRING_VALUES),
            operator=self.random.choice(STRING_OPERATORS),
            operand=self.random.choice(STRING_VALUES),
        )


class RandomInputGenerator(object):
    """Generate unique, reproducible inputs without target feedback."""

    def __init__(self, seed):
        self.domain = InputDomain(seed)
        self.seen = set()
        self.random = self.domain.random

    def next_candidate(self):
        for _attempt in range(2000):
            candidate = self.domain.sample()
            identifier = candidate.identifier()
            if identifier not in self.seen:
                self.seen.add(identifier)
                return candidate
        raise RuntimeError(
            "Input domain exhausted while generating unique random candidates"
        )

    def generate(self, count):
        candidates = []
        generation_seconds = []
        for _ in range(count):
            started = time.perf_counter()
            candidate = self.next_candidate()
            generation_seconds.append(time.perf_counter() - started)
            candidates.append(candidate)
        return candidates, generation_seconds


def input_from_candidate(candidate):
    return candidate.to_test_input()