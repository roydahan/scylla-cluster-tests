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

"""Reporting the datacenter and the rack names of the DB nodes to Argus after the nodes started.

`node.datacenter` and `node.node_rack` each run `nodetool status` on the node itself. `wait_for_init` asked the
nodes for them one by one, about 1.4s per node; `BaseScyllaCluster.update_rack_info_in_argus` reads the names of
all the nodes from one `nodetool status` instead.
"""

from unittest.mock import MagicMock

import pytest

from sdcm.cluster import BaseCluster, BaseNode, BaseScyllaCluster, wait_for_init_wrap


class _Node(BaseNode):
    def __init__(self, name, parent_cluster):  # skip the full BaseNode.__init__
        self.name = name
        self.parent_cluster = parent_cluster
        self._datacenter_name = None
        self._node_rack = None
        self.update_rack_info_in_argus = MagicMock()
        self.update_shards_in_argus = MagicMock()
        self.get_nodes_status = MagicMock(return_value={})
        self._is_node_ready_run_scylla_commands = MagicMock(return_value=True)

    region = "eu-west-1"

    def __str__(self):
        return self.name

    def reported_names(self):
        return self.update_rack_info_in_argus.call_args.args


class _ScyllaCluster(BaseScyllaCluster, BaseCluster):
    node_type = "scylla-db"
    parallel_startup = True

    def __init__(self, nodes_count=0):  # skip the full cluster __init__
        self.name = "db-cluster"
        self.log = MagicMock()
        self.nodes = [_Node(f"node-{idx}", parent_cluster=self) for idx in range(nodes_count)]
        # what a node finds when it has to run `nodetool status` on itself
        self.get_datacenter_name_per_region = MagicMock(return_value={_Node.region: "dc-asked"})
        self.get_rack_names_per_datacenter_and_rack_idx = MagicMock(return_value={(_Node.region, "0"): "rack-asked"})
        self.update_db_binary = MagicMock()
        self.update_db_packages = MagicMock()
        self.wait_for_nodes_up_and_normal = MagicMock()
        self.node_setup = MagicMock()
        self.node_startup = MagicMock()

    @wait_for_init_wrap
    def wait_for_init(self, node_list=None, timeout=None):
        pass


def _status(nodes):
    return {node: {"status": "UN", "dc": "dc-status", "rack": f"rack-{node.name}"} for node in nodes}


def test_names_of_all_nodes_come_from_one_nodetool_status():
    cluster = _ScyllaCluster(nodes_count=5)
    verification_node = cluster.nodes[0]
    verification_node.get_nodes_status.return_value = _status(cluster.nodes)

    cluster.update_rack_info_in_argus(nodes=cluster.nodes, verification_node=verification_node)

    verification_node.get_nodes_status.assert_called_once_with(nodes=cluster.nodes)
    for node in cluster.nodes[1:]:
        node.get_nodes_status.assert_not_called()
    # no node ran `nodetool status` on itself
    cluster.get_datacenter_name_per_region.assert_not_called()
    cluster.get_rack_names_per_datacenter_and_rack_idx.assert_not_called()
    assert [node.reported_names() for node in cluster.nodes] == [
        ("dc-status", f"rack-{node.name}") for node in cluster.nodes
    ]


def test_first_node_is_the_default_verification_node_and_all_cluster_nodes_the_default_nodes():
    cluster = _ScyllaCluster(nodes_count=3)
    cluster.nodes[0].get_nodes_status.return_value = _status(cluster.nodes)

    cluster.update_rack_info_in_argus()

    cluster.nodes[0].get_nodes_status.assert_called_once_with(nodes=cluster.nodes)
    assert all(node.update_rack_info_in_argus.call_count == 1 for node in cluster.nodes)


def test_node_missing_from_the_status_is_asked_itself():
    cluster = _ScyllaCluster(nodes_count=3)
    missing = cluster.nodes[2]
    cluster.nodes[0].get_nodes_status.return_value = _status(cluster.nodes[:2])

    cluster.update_rack_info_in_argus(nodes=cluster.nodes)

    cluster.get_datacenter_name_per_region.assert_called_once_with(db_nodes=[missing])
    cluster.get_rack_names_per_datacenter_and_rack_idx.assert_called_once_with(db_nodes=[missing])
    assert missing.reported_names() == ("dc-asked", "rack-asked")
    assert cluster.nodes[1].reported_names() == ("dc-status", "rack-node-1")


def test_names_a_node_already_knows_are_kept():
    cluster = _ScyllaCluster(nodes_count=2)
    known = cluster.nodes[1]
    known.cache_dc_and_rack_names(dc_name="dc-known", rack_name="rack-known")
    cluster.nodes[0].get_nodes_status.return_value = _status(cluster.nodes)

    cluster.update_rack_info_in_argus(nodes=cluster.nodes)

    assert known.reported_names() == ("dc-known", "rack-known")


def test_failure_of_one_node_does_not_stop_the_others():
    cluster = _ScyllaCluster(nodes_count=3)
    cluster.nodes[0].get_nodes_status.return_value = _status(cluster.nodes)
    cluster.nodes[1].update_rack_info_in_argus.side_effect = RuntimeError("argus is down")

    cluster.update_rack_info_in_argus(nodes=cluster.nodes)

    assert all(node.update_rack_info_in_argus.call_count == 1 for node in cluster.nodes)


def test_no_nodes_is_a_noop():
    cluster = _ScyllaCluster(nodes_count=0)

    cluster.update_rack_info_in_argus(nodes=[])


# --- wait_for_init_wrap ---


def test_wait_for_init_reports_the_new_scylla_nodes_from_one_status_of_the_first_of_them():
    cluster = _ScyllaCluster(nodes_count=4)
    new_nodes = cluster.nodes[2:]
    new_nodes[0].get_nodes_status.return_value = _status(new_nodes)
    for node in new_nodes:  # Scylla is down during the node setup, so a node has no names to report then
        node._is_node_ready_run_scylla_commands.return_value = False

    def node_startup(node, **_):
        node._is_node_ready_run_scylla_commands.return_value = True

    cluster.node_startup.side_effect = node_startup

    cluster.wait_for_init(node_list=new_nodes, critical_node_setup_events=[])

    new_nodes[0].get_nodes_status.assert_called_once_with(nodes=new_nodes)
    cluster.get_datacenter_name_per_region.assert_not_called()
    cluster.get_rack_names_per_datacenter_and_rack_idx.assert_not_called()
    for node in new_nodes:
        # the last report of a node, after the nodes started
        assert node.reported_names() == ("dc-status", f"rack-{node.name}")
    for node in cluster.nodes[:2]:
        node.update_rack_info_in_argus.assert_not_called()


class _LoaderSet(BaseCluster):
    parallel_startup = True

    def __init__(self, nodes):  # skip the full cluster __init__
        self.name = "loader-set"
        self.log = MagicMock()
        self.nodes = nodes
        self.node_setup = MagicMock()
        self.node_startup = MagicMock()

    @wait_for_init_wrap
    def wait_for_init(self, node_list=None, timeout=None):
        pass


@pytest.mark.parametrize("failing", [False, True], ids=["all-reported", "one-node-fails"])
def test_wait_for_init_of_a_non_scylla_cluster_still_reports_every_node_itself(failing):
    nodes = []
    for idx in range(3):
        node = MagicMock(datacenter="eu-west-1", node_rack=str(idx))
        node.name = f"loader-{idx}"
        nodes.append(node)
    if failing:
        nodes[0].update_rack_info_in_argus.side_effect = [None, RuntimeError("argus is down")]

    _LoaderSet(nodes).wait_for_init(critical_node_setup_events=[])

    for idx, node in enumerate(nodes):
        node.update_rack_info_in_argus.assert_called_with("eu-west-1", str(idx))
        assert node.update_rack_info_in_argus.call_count == 2  # once in the node setup, once after the startup
