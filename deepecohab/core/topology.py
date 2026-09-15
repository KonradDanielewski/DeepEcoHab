from collections import deque


def antennas(antenna_combinations: dict[str, str]) -> set[str]:
	"""The antennas the layout names.

	Args:
		antenna_combinations: the layout's antenna pair to position map.
	"""
	return {antenna for pair in antenna_combinations for antenna in pair.split("_")}


def step_graph(antenna_combinations: dict[str, str]) -> dict[str, set[str]]:
	"""The antennas reachable from each antenna in one step.

	Args:
		antenna_combinations: the layout's antenna pair to position map.

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

	Args:
		antenna_combinations: the layout's antenna pair to position map.

	Returns:
		The antennas crossed, in order, keyed by the antennas the step was seen
		between.
	"""
	graph = step_graph(antenna_combinations)
	return {
		(source, target): route
		for source in graph
		for target, route in _shortest_routes(graph, source).items()
		if target not in graph[source]
	}


def _shortest_routes(graph: dict[str, set[str]], source: str) -> dict[str, list[str]]:
	"""Intermediate antennas of the one shortest route from ``source``, per target.

	Breadth-first. ``None`` marks a node that several equally short routes reach, and
	a target is reported only when neither it nor any node behind it carries the mark.
	"""
	predecessor: dict[str, str | None] = {}
	distance = {source: 0}
	queue = deque([source])
	while queue:
		node = queue.popleft()
		for step in graph[node]:
			if step not in distance:
				distance[step] = distance[node] + 1
				predecessor[step] = node
				queue.append(step)
			elif distance[step] == distance[node] + 1:
				predecessor[step] = None

	routes: dict[str, list[str]] = {}
	# In discovery order, so a node's predecessor is always settled before the node.
	for target, node in predecessor.items():
		if node == source:
			routes[target] = []
		elif node in routes:
			routes[target] = routes[node] + [node]
	return routes
