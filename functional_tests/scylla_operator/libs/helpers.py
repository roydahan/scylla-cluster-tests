#!/usr/bin/env python

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
# Copyright (c) 2021 ScyllaDB
import yaml

from sdcm.cluster_k8s import SCYLLA_NAMESPACE, SCYLLA_OPERATOR_NAMESPACE, ScyllaPodCluster


def get_orphaned_services(db_cluster):
    pod_names = scylla_pod_names(db_cluster)
    services_names = scylla_services_names(db_cluster)
    return list(set(services_names) - set(pod_names))


def scylla_pod_names(db_cluster):
    pods = db_cluster.k8s_cluster.kubectl(f"get pods -n {SCYLLA_NAMESPACE} -l scylla/cluster=sct-cluster "
                                          f"-o=custom-columns='NAME:.metadata.name'")

    return [name for name in pods.stdout.split() if name != 'NAME']


def scylla_services_names(db_cluster):
    services = db_cluster.k8s_cluster.kubectl(f"get svc -n {SCYLLA_NAMESPACE} -l scylla/cluster=sct-cluster "
                                              f"-o=custom-columns='NAME:.metadata.name'")
    return [name for name in services.stdout.split() if name not in ('NAME', 'sct-cluster-client')]


def rollout_restart(db_cluster: ScyllaPodCluster, namespace: str, deployment: str = None):
    db_cluster.k8s_cluster.kubectl(f"rollout restart deployment -n {namespace} {deployment if deployment else ''}")


def scylla_operator_rollout_restart(db_cluster: ScyllaPodCluster):
    rollout_restart(db_cluster, namespace=SCYLLA_OPERATOR_NAMESPACE)


def get_deployment_rollout_status(db_cluster: ScyllaPodCluster, namespace: str, deployment: str, timeout: str):
    return db_cluster.k8s_cluster.kubectl(f"rollout status deployment -n {namespace} {deployment} --timeout={timeout}")


def wait_for_scylla_operator_rollout_complete(db_cluster: ScyllaPodCluster, timeout: str = '60s'):
    status = []
    for deployment in ['scylla-operator', 'webhook-server']:
        deployment_rollout_status = get_deployment_rollout_status(db_cluster, namespace=SCYLLA_OPERATOR_NAMESPACE,
                                                                  deployment=deployment, timeout=timeout)
        if f"deployment \"{deployment}\" successfully rolled out" not in deployment_rollout_status.stdout:
            status.append(f"{deployment}: {deployment_rollout_status.stdout}")
    return status


def scylla_operator_pods_and_statuses(db_cluster):
    pods = db_cluster.k8s_cluster.kubectl(f"get pods -n {SCYLLA_OPERATOR_NAMESPACE} "
                                          f"-l app.kubernetes.io/instance=scylla-operator "
                                          f"-o=custom-columns='NAME:.metadata.name,STATUS:.status.phase' -o yaml")

    return [[pod["metadata"]["name"], pod["status"]["phase"]] for pod in yaml.load(pods.stdout)["items"] if pod]
