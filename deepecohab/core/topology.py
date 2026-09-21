import itertools


def antennas(antenna_combinations: dict[str, str]) -> set[str]:
	"""The antennas the layout names."""
	return {antenna for pair in antenna_combinations for antenna in pair.split("_")}


def step_graph(antenna_combinations: dict[str, str]) -> dict[str, set[str]]:
	"""The antennas reachable from each antenna in one step.

	Returns:
		One entry per antenna in the layout, holding the antennas a legal single step
		leads to.
	"""
	graph: dict[str, set[str]] = {antenna: set() for antenna in antennas(antenna_combinations)}
	for pair in antenna_combinations:
		source, target = pair.split("_")
		if source != target:
			graph[source].add(target)
	return graph


def unique_routes(antenna_combinations: dict[str, str]) -> dict[tuple[str, str], list[str]]:
	"""The antennas an animal must have crossed for each step the layout forbids.

	A step between two antennas the layout does not join is only possible if the
	antennas in between failed to read. Where more than one route is equally short
	there is no telling which antennas those were, and the step is left out.

	Returns:
		The antennas crossed, in order, keyed by the antennas the step was seen
		between.
	"""
	# Imported here rather than at module scope: networkx costs ~150ms to import and
	# core is kept cheap to import (test_core_does_not_import_plotting).
	import networkx as nx

	steps = step_graph(antenna_combinations)
	graph = nx.DiGraph({antenna: list(targets) for antenna, targets in steps.items()})

	routes: dict[tuple[str, str], list[str]] = {}
	for source, target in itertools.permutations(graph, 2):
		if target in steps[source] or not nx.has_path(graph, source, target):
			continue
		shortest = itertools.islice(nx.all_shortest_paths(graph, source, target), 2)
		match list(shortest):
			case [path]:
				routes[source, target] = path[1:-1]

	return routes
