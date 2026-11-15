# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#
# See LICENSE for more details.
#
# Copyright (c) 2026 ScyllaDB

"""Tests for the per-node teardown work that runs on the nodes of a cluster at the same time.

Covers `run_teardown_on_nodes`, `ClusterTester.stop_resources_stop_tasks_threads` and `BaseCluster.get_backtraces`.
"""

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from sdcm.cluster import BaseCluster, run_teardown_on_nodes
from sdcm.tester import ClusterTester

# how long the work of a node waits for the work of the other nodes, a serial run fails after it
OVERLAP_TIMEOUT = 10
CLUSTER_NAME = "db-cluster"
SILENCED_NAME = f"stop_resources_stop_tasks_threads(cluster={CLUSTER_NAME})"


def _make_nodes(count):
    nodes = []
    for idx in range(count):
        node = MagicMock()
        node.name = f"node-{idx}"
        node.n_coredumps = 0
        nodes.append(node)
    return nodes


def _wait_for_all(barrier):
    """Build a side effect that returns only after all the parties of `barrier` called it."""

    def side_effect(*_, **__):
        barrier.wait(timeout=OVERLAP_TIMEOUT)

    return side_effect


class _Cluster(BaseCluster):
    def __init__(self, nodes):
        self.nodes = nodes
        self.coredumps = {}
        self.log = MagicMock()


# --- run_teardown_on_nodes ---


def test_run_teardown_on_nodes_runs_nodes_at_the_same_time_and_keeps_their_order():
    nodes = _make_nodes(5)
    barrier = threading.Barrier(len(nodes))

    def func(node):
        barrier.wait(timeout=OVERLAP_TIMEOUT)
        return node.name

    assert run_teardown_on_nodes(func, nodes) == [node.name for node in nodes]


def test_run_teardown_on_nodes_caps_the_workers(monkeypatch):
    monkeypatch.setattr("sdcm.cluster.TEARDOWN_NODES_MAX_WORKERS", 3)
    lock = threading.Lock()
    active = 0
    max_active = 0

    def func(_):
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.05)
        with lock:
            active -= 1

    run_teardown_on_nodes(func, _make_nodes(10))

    assert max_active == 3


def test_run_teardown_on_nodes_processes_every_node_when_one_raises(monkeypatch):
    # with one worker the nodes after the failed one are still queued when it fails
    monkeypatch.setattr("sdcm.cluster.TEARDOWN_NODES_MAX_WORKERS", 1)
    nodes = _make_nodes(4)
    processed = []

    def func(node):
        processed.append(node.name)
        if node.name in ("node-1", "node-2"):
            raise ValueError(node.name)

    with pytest.raises(ValueError, match="node-1"):
        run_teardown_on_nodes(func, nodes)

    assert processed == [node.name for node in nodes]


def test_run_teardown_on_nodes_without_nodes():
    func = MagicMock()

    assert run_teardown_on_nodes(func, []) == []
    func.assert_not_called()


# --- ClusterTester.stop_resources_stop_tasks_threads ---


@pytest.fixture
def framework_event():
    with patch("sdcm.tester.TestFrameworkEvent") as event:
        yield event


def _stop_resources_stop_tasks_threads(nodes):
    cluster = MagicMock()
    cluster.nodes = nodes
    cluster.__str__.return_value = CLUSTER_NAME
    return ClusterTester.stop_resources_stop_tasks_threads(MagicMock(), cluster)


def test_stop_tasks_threads_stops_all_nodes_before_waiting_for_any(framework_event):
    nodes = _make_nodes(5)
    lock = threading.Lock()
    calls = []

    def record(action, node):
        def side_effect(*_, **__):
            with lock:
                calls.append((action, node.name))

        return side_effect

    for node in nodes:
        node.stop_task_threads.side_effect = record("stop", node)
        node.wait_till_tasks_threads_are_stopped.side_effect = record("wait", node)

    _stop_resources_stop_tasks_threads(nodes)

    assert calls[: len(nodes)] == [("stop", node.name) for node in nodes]
    assert sorted(calls[len(nodes) :]) == [("wait", node.name) for node in nodes]
    framework_event.assert_not_called()


def test_stop_tasks_threads_waits_for_the_nodes_at_the_same_time(framework_event):
    nodes = _make_nodes(5)
    barrier = threading.Barrier(len(nodes))
    for node in nodes:
        node.wait_till_tasks_threads_are_stopped.side_effect = _wait_for_all(barrier)

    _stop_resources_stop_tasks_threads(nodes)

    for node in nodes:
        node.wait_till_tasks_threads_are_stopped.assert_called_once_with()
    framework_event.assert_not_called()


def test_stop_tasks_threads_silences_the_failure_of_a_node_and_waits_for_the_others(framework_event):
    nodes = _make_nodes(5)
    error = RuntimeError("node-1 threads are stuck")
    nodes[1].wait_till_tasks_threads_are_stopped.side_effect = error

    assert _stop_resources_stop_tasks_threads(nodes) is None

    for node in nodes:
        node.wait_till_tasks_threads_are_stopped.assert_called_once_with()
    framework_event.assert_called_once()
    assert framework_event.call_args.kwargs["source_method"] == SILENCED_NAME
    assert framework_event.call_args.kwargs["exception"] is error


# --- BaseCluster.get_backtraces ---


def test_get_backtraces_checks_the_nodes_at_the_same_time():
    nodes = _make_nodes(5)
    barrier = threading.Barrier(len(nodes))
    for node in nodes:
        node.get_backtraces.side_effect = _wait_for_all(barrier)
        node.n_coredumps = 1
    cluster = _Cluster(nodes)

    cluster.get_backtraces()

    cluster.log.exception.assert_not_called()
    assert cluster.coredumps == {node.name: 1 for node in nodes}


def test_get_backtraces_fills_coredumps_of_the_nodes_that_have_them():
    nodes = _make_nodes(4)
    for node, n_coredumps in zip(nodes, [0, 2, 0, 5], strict=True):
        node.n_coredumps = n_coredumps
    cluster = _Cluster(nodes)
    cluster.coredumps["node-from-before"] = 1

    cluster.get_backtraces()

    for node in nodes:
        node.get_backtraces.assert_called_once_with()
    assert cluster.coredumps == {"node-from-before": 1, "node-1": 2, "node-3": 5}


def test_get_backtraces_logs_the_failure_of_a_node_and_checks_the_others():
    nodes = _make_nodes(4)
    for node in nodes:
        node.n_coredumps = 3
    nodes[1].get_backtraces.side_effect = RuntimeError("SSH to node-1 failed")
    cluster = _Cluster(nodes)

    cluster.get_backtraces()

    for node in nodes:
        node.get_backtraces.assert_called_once_with()
    cluster.log.exception.assert_called_once()
    assert "SSH to node-1 failed" in cluster.log.exception.call_args.args[0]
    assert cluster.coredumps == {"node-0": 3, "node-2": 3, "node-3": 3}
