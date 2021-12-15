import unittest
import time
import inspect
import logging

from collections import namedtuple
from sdcm.nemesis import Nemesis
from sdcm.cluster_aws import ScyllaAWSCluster
from sdcm.log import SDCMAdapter


PARAMS = dict(nemesis_interval=1, nemesis_filter_seeds=False)
Cluster = namedtuple("Cluster", ['params'])
FakeTester = namedtuple("FakeTester", ['params', 'loaders', 'monitors', 'db_cluster'],
                        defaults=[PARAMS, {}, {}, Cluster(params=PARAMS)])


class FakeScyllaAWSCluster(ScyllaAWSCluster):
    def __init__(self, params: dict = None):
        self.params = params


# pylint: disable=redefined-outer-name,protected-access,too-few-public-methods
class FakeTester:
    def __init__(self, db_cluster):
        self.params = {'nemesis_filter': ['disruptive'], 'nemesis_multiply_factor': 1}
        db_cluster.params = self.params
        self.db_cluster = db_cluster
        self.loaders = None
        self.monitors = None


class FakeNemesis(Nemesis):
    disruptive = False
    run_with_gemini = True
    networking = False
    kubernetes = False
    limited = False
    MINUTE_IN_SEC = 60
    HOUR_IN_SEC = 60 * MINUTE_IN_SEC
    disruptions_list = []
    has_steady_run = False
    DISRUPT_NAME_PREF = "disrupt_"

    def __new__(cls, tester_obj, termination_event, *args):
        return object.__new__(cls)

    def disrupt(self):
        pass

    def __init__(self, tester_obj, termination_event):  # pylint: disable=unused-argument
        self.target_node = None
        self.start_time = time.time()
        self.stats = {}
        self.tester = tester_obj  # ClusterTester object
        self.cluster = tester_obj.db_cluster
        logger = logging.getLogger(__name__)
        self.log = SDCMAdapter(logger, extra={'prefix': str(self)})
        #super().__init__(tester_obj, termination_event)

    def disrupt_hard_reboot_node(self):
        print('PASSED {}'.format(inspect.stack()[0][3]))
        return 'PASSED {}'.format(inspect.stack()[0][3])

    @staticmethod
    def disrupt_only_disruptive():
        print('PASSED {}'.format(inspect.stack()[0][3]))
        return 'PASSED {}'.format(inspect.stack()[0][3])

    @staticmethod
    def disrupt_only_kuberntis():
        print('PASSED {}'.format(inspect.stack()[0][3]))
        return 'PASSED {}'.format(inspect.stack()[0][3])

    @staticmethod
    def disrupt_only_limited():
        print('PASSED {}'.format(inspect.stack()[0][3]))
        return 'PASSED {}'.format(inspect.stack()[0][3])

    @staticmethod
    def disrupt_disruptive_and_kuberntis():
        print('PASSED {}'.format(inspect.stack()[0][3]))
        return 'PASSED {}'.format(inspect.stack()[0][3])


class HardRebootNodeMonkey(FakeNemesis):
    disruptive = True
    kubernetes = True
    limited = True

    def disrupt(self):
        self.disrupt_hard_reboot_node()


class OnlyDisruptive(FakeNemesis):
    disruptive = True

    def disrupt(self):
        self.disrupt_only_disruptive()


class OnlyKubernetes(FakeNemesis):
    kubernetes = True
    run_with_gemini = False

    def disrupt(self):
        self.disrupt_only_kuberntis()


class OnlyLimited(FakeNemesis):
    # disruptive = True
    # kubernetes = True
    limited = True

    def disrupt(self):
        self.disrupt_only_limited()


class DisruptiveAndkubernetes(FakeNemesis):
    disruptive = True
    kubernetes = True
    run_with_gemini = False

    def disrupt(self):
        self.disrupt_disruptive_and_kuberntis()


class SisyphusTests(unittest.TestCase):

    def test_only_disruptive(self):
        nemesis = FakeNemesis(tester_obj=FakeTester(FakeScyllaAWSCluster()), termination_event=None)
        disrupt_list = nemesis.build_list_of_disruptions_to_execute(nemesis_filter=['disruptive'])
        self.assertEqual(3, len(disrupt_list), msg='Disruption list length not as expected')
        print(disrupt_list)
        while disrupt_list:
            next_disrupt = disrupt_list.pop()
            assert next_disrupt.__name__ in ['disrupt_only_disruptive', 'disrupt_hard_reboot_node',
                                             'disrupt_disruptive_and_kuberntis']
            nemesis.execute_disrupt_method(disrupt_method=next_disrupt)

    def test_only_limited(self):
        nemesis = FakeNemesis(tester_obj=FakeTester(FakeScyllaAWSCluster()), termination_event=None)
        disrupt_list = nemesis.build_list_of_disruptions_to_execute(nemesis_filter=['limited'])
        self.assertEqual(2, len(disrupt_list), msg='Disruption list length not as expected')
        print(disrupt_list)
        while disrupt_list:
            next_disrupt = disrupt_list.pop()
            assert next_disrupt.__name__ in ['disrupt_only_limited', 'disrupt_hard_reboot_node']
            nemesis.execute_disrupt_method(disrupt_method=next_disrupt)

    def test_disruptive_and_kubernetes(self):
        nemesis = FakeNemesis(tester_obj=FakeTester(FakeScyllaAWSCluster()), termination_event=None)
        disrupt_list = nemesis.build_list_of_disruptions_to_execute(nemesis_filter=['disruptive', 'kubernetes'])
        self.assertEqual(2, len(disrupt_list), msg='Disruption list length not as expected')
        print(disrupt_list)
        while disrupt_list:
            next_disrupt = disrupt_list.pop()
            assert next_disrupt.__name__ in ['disrupt_disruptive_and_kuberntis', 'disrupt_hard_reboot_node']
            nemesis.execute_disrupt_method(disrupt_method=next_disrupt)

    def test_disruptive_kubernetes_and_limited(self):
        nemesis = FakeNemesis(tester_obj=FakeTester(FakeScyllaAWSCluster()), termination_event=None)
        disrupt_list = nemesis.build_list_of_disruptions_to_execute(nemesis_filter=['disruptive', 'kubernetes',
                                                                                    'limited'])
        self.assertEqual(1, len(disrupt_list), msg='Disruption list length not as expected')
        print(disrupt_list)
        while disrupt_list:
            next_disrupt = disrupt_list.pop()
            assert next_disrupt.__name__ in ['disrupt_hard_reboot_node']
            nemesis.execute_disrupt_method(disrupt_method=next_disrupt)

    def test_non_exsitent_property(self):
        nemesis = FakeNemesis(tester_obj=FakeTester(FakeScyllaAWSCluster()), termination_event=None)
        disrupt_list = nemesis.build_list_of_disruptions_to_execute(nemesis_filter=['not-exist'])
        self.assertEqual(5, len(disrupt_list), msg='Disruption list length not as expected')
        print(disrupt_list)
        while disrupt_list:
            next_disrupt = disrupt_list.pop()
            assert next_disrupt.__name__ in ['disrupt_only_disruptive', 'disrupt_hard_reboot_node',
                                             'disrupt_disruptive_and_kuberntis', 'disrupt_only_limited',
                                             'disrupt_only_kuberntis']
            nemesis.execute_disrupt_method(disrupt_method=next_disrupt)

    def test_intersection_with_non_exist(self):
        nemesis = FakeNemesis(tester_obj=FakeTester(FakeScyllaAWSCluster()), termination_event=None)
        disrupt_list = nemesis.build_list_of_disruptions_to_execute(nemesis_filter=['disruptive', 'not-exist'])
        self.assertEqual(3, len(disrupt_list), msg='Disruption list length not as expected')
        print(disrupt_list)
        while disrupt_list:
            next_disrupt = disrupt_list.pop()
            assert next_disrupt.__name__ in ['disrupt_only_disruptive', 'disrupt_hard_reboot_node',
                                             'disrupt_disruptive_and_kuberntis']
            nemesis.execute_disrupt_method(disrupt_method=next_disrupt)

    def test_without_filter(self):
        nemesis = FakeNemesis(tester_obj=FakeTester(FakeScyllaAWSCluster()), termination_event=None)
        disrupt_list = nemesis.build_list_of_disruptions_to_execute()
        self.assertEqual(5, len(disrupt_list), msg='Disruption list length not as expected')
        print(disrupt_list)
        while disrupt_list:
            next_disrupt = disrupt_list.pop()
            assert next_disrupt.__name__ in ['disrupt_only_disruptive', 'disrupt_hard_reboot_node',
                                             'disrupt_disruptive_and_kuberntis', 'disrupt_only_limited',
                                             'disrupt_only_kuberntis']
            nemesis.execute_disrupt_method(disrupt_method=next_disrupt)

    def test_with_filter_and_multiply(self):
        nemesis = FakeNemesis(tester_obj=FakeTester(FakeScyllaAWSCluster()), termination_event=None)
        disrupt_list = nemesis.build_list_of_disruptions_to_execute(nemesis_filter=['disruptive', 'kubernetes',
                                                                                    'not-exist'],
                                                                    nemesis_multiply_factor=5)
        self.assertEqual(10, len(disrupt_list), msg='Disruption list length not as expected')
        print(disrupt_list)
        while disrupt_list:
            next_disrupt = disrupt_list.pop()
            assert next_disrupt.__name__ in ['disrupt_hard_reboot_node', 'disrupt_disruptive_and_kuberntis']
            nemesis.execute_disrupt_method(disrupt_method=next_disrupt)
