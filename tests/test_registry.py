"""Tests for DataFrameRegistry dependency resolution (_resolve_order).

The topological sort is the one piece of pipeline orchestration that is pure and
free of I/O, so it is unit-testable in isolation. We build throwaway registries
with register_step (the lifecycle body never runs here) and assert ordering
invariants, plus a few checks against the real df_registry.
"""

import pytest

from deepecohab.core.registries import DataFrameRegistry, df_registry


def _make(deps: dict[str, list[str]]) -> DataFrameRegistry:
	"""Build a registry whose steps have the given requires-edges."""
	reg = DataFrameRegistry()
	for name, requires in deps.items():

		@reg.register_step(name, requires=requires)
		def _step(cfg, **kwargs):  # pragma: no cover - never executed
			return None

	return reg


def _is_topo(order: list[str], deps: dict[str, list[str]]) -> bool:
	"""Every dependency that is itself a step must appear before its dependant."""
	pos = {name: i for i, name in enumerate(order)}
	steps = set(deps)
	return all(
		pos[req] < pos[name] for name, requires in deps.items() for req in requires if req in steps
	)


def test_linear_chain_orders_dependencies_first():
	deps = {"a": [], "b": ["a"], "c": ["b"]}
	assert _make(deps)._resolve_order() == ["a", "b", "c"]


def test_external_requires_create_no_edge():
	# "main_df" is not a registered step -> treated as external prerequisite.
	deps = {"x": ["main_df"], "y": ["main_df"]}
	order = _make(deps)._resolve_order()
	assert sorted(order) == ["x", "y"]


def test_diamond_is_valid_topological_order():
	deps = {"root": [], "left": ["root"], "right": ["root"], "join": ["left", "right"]}
	reg = _make(deps)
	order = reg._resolve_order()
	assert _is_topo(order, deps)
	assert order[0] == "root" and order[-1] == "join"


def test_order_is_deterministic():
	deps = {"a": [], "b": [], "c": ["a", "b"]}
	reg = _make(deps)
	assert reg._resolve_order() == reg._resolve_order()


def test_targets_returns_only_transitive_closure():
	deps = {"a": [], "b": ["a"], "c": ["b"], "other": []}
	order = _make(deps)._resolve_order(targets=["c"])
	assert order == ["a", "b", "c"]
	assert "other" not in order


def test_cycle_raises():
	deps = {"a": ["b"], "b": ["a"]}
	with pytest.raises(ValueError, match="Cycle"):
		_make(deps)._resolve_order()


def test_unknown_target_raises():
	with pytest.raises(KeyError):
		_make({"a": []})._resolve_order(targets=["nope"])


def test_real_pipeline_order_respects_dependencies():
	order = df_registry.analysis_steps
	# match_df must precede its consumers; feature inputs precede feature_df.
	assert order.index("match_df") < order.index("chasings_df")
	assert order.index("match_df") < order.index("ranking")
	for dep in ("chasings_df", "tube_test_df", "pairwise_meetings", "activity_df"):
		assert order.index(dep) < order.index("feature_df")
