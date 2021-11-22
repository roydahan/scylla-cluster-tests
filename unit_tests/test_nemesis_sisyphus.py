import unittest
import time
import inspect

from collections import namedtuple
from sdcm.nemesis import Nemesis

PARAMS = dict(nemesis_interval=1, nemesis_filter_seeds=False)
Cluster = namedtuple("Cluster", ['params'])
FakeTester = namedtuple("FakeTester", ['params', 'loaders', 'monitors', 'db_cluster'],
                        defaults=[PARAMS, {}, {}, Cluster(params=PARAMS)])


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

    def __init__(self):  # pylint: disable=unused-argument
        self.target_node = None
        self.start_time = time.time()
        self.stats = {}

    def disrupt_hard_reboot_node(self):
        print('PASSED {}'.format(inspect.stack()[0][3]))
        return 'PASSED {}'.format(inspect.stack()[0][3])

    def disrupt_only_disruptive(self):
        print('PASSED {}'.format(inspect.stack()[0][3]))
        return 'PASSED {}'.format(inspect.stack()[0][3])

    def disrupt_only_kuberntis(self):
        print('PASSED {}'.format(inspect.stack()[0][3]))
        return 'PASSED {}'.format(inspect.stack()[0][3])

    def disrupt_only_limited(self):
        print('PASSED {}'.format(inspect.stack()[0][3]))
        return 'PASSED {}'.format(inspect.stack()[0][3])

    def disrupt_disruptive_and_kuberntis(self):
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

    def __new__(cls, tester_obj, termination_event, *args):
        return object.__new__(cls)

    def disrupt(self):
        pass


class SisyphusTests(unittest.TestCase):

    def test_only_disruptive(self):
        n = Nemesis()
        disrupt_list = n.build_list_of_disruptions_to_execute(nemesis_filter=['disruptive'])
        self.assertEqual(3, len(disrupt_list), msg='Disruption list length not as expected')
        print(disrupt_list)
        while disrupt_list:
            next_disrupt = disrupt_list.pop()
            assert next_disrupt.__name__ in ['disrupt_only_disruptive', 'disrupt_hard_reboot_node',
                                             'disrupt_disruptive_and_kuberntis']
            n.execute_disrupt_method(disrupt_method=next_disrupt)

    def test_only_limited(self):
        n = Nemesis()
        disrupt_list = n.build_list_of_disruptions_to_execute(nemesis_filter=['limited'])
        self.assertEqual(2, len(disrupt_list), msg='Disruption list length not as expected')
        print(disrupt_list)
        while disrupt_list:
            next_disrupt = disrupt_list.pop()
            assert next_disrupt.__name__ in ['disrupt_only_limited', 'disrupt_hard_reboot_node']
            n.execute_disrupt_method(disrupt_method=next_disrupt)

    def test_disruptive_and_kubernetes(self):
        n = Nemesis()
        disrupt_list = n.build_list_of_disruptions_to_execute(nemesis_filter=['disruptive', 'kubernetes'])
        self.assertEqual(2, len(disrupt_list), msg='Disruption list length not as expected')
        print(disrupt_list)
        while disrupt_list:
            next_disrupt = disrupt_list.pop()
            assert next_disrupt.__name__ in ['disrupt_disruptive_and_kuberntis', 'disrupt_hard_reboot_node']
            n.execute_disrupt_method(disrupt_method=next_disrupt)

    def test_disruptive_kubernetes_and_limited(self):
        n = Nemesis()
        disrupt_list = n.build_list_of_disruptions_to_execute(nemesis_filter=['disruptive', 'kubernetes', 'limited'])
        self.assertEqual(1, len(disrupt_list), msg='Disruption list length not as expected')
        print(disrupt_list)
        while disrupt_list:
            next_disrupt = disrupt_list.pop()
            assert next_disrupt.__name__ in ['disrupt_hard_reboot_node']
            n.execute_disrupt_method(disrupt_method=next_disrupt)

    def test_non_exsitent_property(self):
        n = Nemesis()
        disrupt_list = n.build_list_of_disruptions_to_execute(nemesis_filter=['not-exist'])
        self.assertEqual(5, len(disrupt_list), msg='Disruption list length not as expected')
        print(disrupt_list)
        while disrupt_list:
            next_disrupt = disrupt_list.pop()
            assert next_disrupt.__name__ in ['disrupt_only_disruptive', 'disrupt_hard_reboot_node',
                                             'disrupt_disruptive_and_kuberntis', 'disrupt_only_limited',
                                             'disrupt_only_kuberntis']
            n.execute_disrupt_method(disrupt_method=next_disrupt)

    def test_intersection_with_non_exist(self):
        n = Nemesis()
        disrupt_list = n.build_list_of_disruptions_to_execute(nemesis_filter=['disruptive', 'not-exist'])
        self.assertEqual(3, len(disrupt_list), msg='Disruption list length not as expected')
        print(disrupt_list)
        while disrupt_list:
            next_disrupt = disrupt_list.pop()
            assert next_disrupt.__name__ in ['disrupt_only_disruptive', 'disrupt_hard_reboot_node',
                                             'disrupt_disruptive_and_kuberntis']
            n.execute_disrupt_method(disrupt_method=next_disrupt)

    def test_without_filter(self):
        n = Nemesis()
        disrupt_list = n.build_list_of_disruptions_to_execute()
        self.assertEqual(5, len(disrupt_list), msg='Disruption list length not as expected')
        print(disrupt_list)
        while disrupt_list:
            next_disrupt = disrupt_list.pop()
            assert next_disrupt.__name__ in ['disrupt_only_disruptive', 'disrupt_hard_reboot_node',
                                             'disrupt_disruptive_and_kuberntis', 'disrupt_only_limited',
                                             'disrupt_only_kuberntis']
            n.execute_disrupt_method(disrupt_method=next_disrupt)

    def test_with_filter_and_multiply(self):
        n = Nemesis()
        disrupt_list = n.build_list_of_disruptions_to_execute(nemesis_filter=['disruptive', 'kubernetes', 'not-exist'],
                                                              nemesis_multiply_factor=5)
        self.assertEqual(10, len(disrupt_list), msg='Disruption list length not as expected')
        print(disrupt_list)
        while disrupt_list:
            next_disrupt = disrupt_list.pop()
            assert next_disrupt.__name__ in ['disrupt_hard_reboot_node', 'disrupt_disruptive_and_kuberntis']
            n.execute_disrupt_method(disrupt_method=next_disrupt)



