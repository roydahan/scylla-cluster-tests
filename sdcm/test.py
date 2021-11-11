import time
import re
import inspect
from typing import List, Optional, Type, Callable, Tuple, Dict, Set, Union



class Nemesis:  # pylint: disable=too-many-instance-attributes,too-many-public-methods

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

    def __init__(self):  # pylint: disable=unused-argument
        self.target_node = None
        self.start_time = time.time()
        self.stats = {}

    def disrupt_hard_reboot_node(self):
        # self.target_node.reboot(hard=True)
        print('Waiting scylla services to start after node reboot')
        # self.target_node.wait_db_up()
        print('Waiting JMX services to start after node reboot')
        # self.target_node.wait_jmx_up()
        # self.cluster.wait_for_nodes_up_and_normal(nodes=[self.target_node])
        print('Done')

    def disrupt_only_disruptive(self):
        print('This is ONLy DISRUPTIVE')

    def disrupt_only_kuberntis(self):
        print('This is ONLy K8S')

    def disrupt_only_limited(self):
        print("I started a disruption ONLY LIMITED")

    def disrupt_disruptive_and_kuberntis(self):
        print('This is DISRUPTIVE AND K8S')


    @classmethod
    def _get_subclasses(cls, **flags):
        tmp = Nemesis.__subclasses__()
        subclasses = []
        while tmp:
            for nemesis in tmp.copy():
                subclasses.append(nemesis)
                tmp.remove(nemesis)
                tmp.extend(nemesis.__subclasses__())
        return cls._get_subclasses_from_list(subclasses, **flags)

    @staticmethod
    def _get_subclasses_from_list(list_of_nemesis, **flags):
        """
        It apply 'and' logic to filter,
            if any value in the filter does not match what nemeses have,
            nemeses will be filtered out.
        """
        nemesis_subclasses = []
        nemesis_to_exclude = 'bla'
        for nemesis in list_of_nemesis:
            matches = True
            for filter_name, filter_value in flags.items():
                if filter_value is None:
                    continue
                try:
                    bug = getattr(nemesis, filter_name)
                except AttributeError:
                    print("caught") #Todo:  Replace with self.log.warning
                    flags[filter_name] = None
                    continue
                if bug != filter_value:
                    matches = False
                    break
            if not matches:
                continue
            nemesis_subclasses.append(nemesis)
        return nemesis_subclasses

    def __str__(self):
        try:
            return str(self.__class__).split("'")[1]
        except Exception:  # pylint: disable=broad-except
            return str(self.__class__)

    def get_list_of_methods_by_flags(self, disruptive=None, run_with_gemini=None, networking=None, kubernetes=None):
        attributes = locals()
        flags = {flag_name: attributes[flag_name] for flag_name in
                 ['disruptive', 'run_with_gemini', 'networking', 'kubernetes'] if
                 attributes[flag_name] is not None}
        subclasses_list = self._get_subclasses(**flags)
        disrupt_methods_list = []
        for subclass in subclasses_list:
            method_name = re.search(
                r'self\.(?P<method_name>disrupt_[A-Za-z_]+?)\(.*\)', inspect.getsource(subclass), flags=re.MULTILINE)
            if method_name:
                disrupt_methods_list.append(method_name.group('method_name'))
        print("Gathered subclass methods: {}".format(disrupt_methods_list))
        return disrupt_methods_list

    def get_list_of_methods_by_property_name(self, list_of_properties_to_include):
        attributes = locals()
        # flags = {flag_name: True for flag_name in
        #          ['disruptive', 'run_with_gemini', 'networking', 'kubernetes', 'limited'] if
        #          flag_name in list_of_properties_to_include}
        flags = {flag_name: True for flag_name in list_of_properties_to_include}
        subclasses_list = self._get_subclasses(**flags)
        disrupt_methods_list = []
        for subclass in subclasses_list:
            method_name = re.search(
                r'self\.(?P<method_name>disrupt_[A-Za-z_]+?)\(.*\)', inspect.getsource(subclass), flags=re.MULTILINE)
            if method_name:
                disrupt_methods_list.append(method_name.group('method_name'))
        print("Gathered subclass methods: {}".format(disrupt_methods_list))
        for method in disrupt_methods_list:
            disrupt_methods = [attr[1] for attr in inspect.getmembers(self) if
                               attr[0] in disrupt_methods_list and
                               callable(attr[1])]
        print("Callable methods: {}".format(disrupt_methods))
        return disrupt_methods

    def execute_disrupt_method(self, disrupt_method):
        disrupt_method_name = disrupt_method.__name__.replace('disrupt_', '')
        print(">>>>>>>>>>>>>Started random_disrupt_method %s" % disrupt_method_name)
        print(disrupt_method_name)
        try:
            disrupt_method()
        except Exception as exc:  # pylint: disable=broad-except
            error_msg = "Exception in random_disrupt_method %s: %s", disrupt_method_name, exc
            print(error_msg)
            #self.error_list.append(error_msg)
            raise
        else:
            print("<<<<<<<<<<<<<Finished random_disrupt_method %s" % disrupt_method_name)
        finally:
            print(disrupt_method_name)

    def get_all_disrupt_methods(self, flag=None, include_list=None):
        #include_list = self.cluster.params.get('nemesis_filter')
        if include_list:
            print(f'For {include_list}:')
            filtered_disruptions = self.get_list_of_methods_by_property_name(list_of_properties_to_include=include_list)
            self.disruptions_list.extend(filtered_disruptions)
            print(filtered_disruptions)
            return filtered_disruptions
        elif flag:
            pass
            # print(f'For Flag:')
            #self.get_list_of_methods_by_flags(disruptive=True)
            # self.get_list_of_methods_by_flags(kubernetes=True)
            # self.get_list_of_methods_by_flags(run_with_gemini=True)
            #return self.get_list_of_methods_by_flags(not_exist=True)
        else:
            all_disruptions = [attr[1] for attr in inspect.getmembers(self)
                               if attr[0].startswith('disrupt_') and callable(attr[1])]
            self.disruptions_list.extend(all_disruptions)
            print(all_disruptions)
            return all_disruptions



class HardRebootNodeMonkey(Nemesis):
    disruptive = True
    kubernetes = True
    limited = True

    def disrupt(self):
        self.disrupt_hard_reboot_node()


class OnlyDisruptive(Nemesis):
    disruptive = True
    #kubernetes = True
    #limited = True

    def disrupt(self):
        self.disrupt_only_disruptive()


class OnlyKuberntis(Nemesis):
    # disruptive = True
    kubernetes = True
    # limited = True
    run_with_gemini = False

    def disrupt(self):
        self.disrupt_only_kuberntis()


class OnlyLimited(Nemesis):
    # disruptive = True
    # kubernetes = True
    limited = True

    def disrupt(self):
        self.disrupt_only_limited()


class Disruptive_and_Kuber(Nemesis):
    disruptive = True
    kubernetes = True
    # limited = True
    run_with_gemini = False

    def disrupt(self):
        self.disrupt_disruptive_and_kuberntis()


if __name__ == "__main__":
    n = Nemesis()
    # list_disruptions = n.get_all_disrupt_methods(include_list=['disruptive'])
    # list_disruptions = n.get_all_disrupt_methods(include_list=['kubernetes'])
    # list_disruptions = n.get_all_disrupt_methods(include_list=['limited'])
    # list_disruptions = n.get_all_disrupt_methods(include_list=['disruptive', 'kubernetes'])
    # list_disruptions = n.get_all_disrupt_methods(include_list=['disruptive', 'kubernetes', 'limited'])
    # list_disruptions = n.get_all_disrupt_methods(include_list=['not-exist'])
    list_disruptions = n.get_all_disrupt_methods(include_list=['disruptive', 'not-exist'])
    # n.get_all_disrupt_methods(include_list=['not-exist', 'disruptive'])
    # n.get_all_disrupt_methods(include_list=['disruptive', 'kubernetes', 'not-exist'])
    # n.get_all_disrupt_methods(flag=1)
    # list_disruptions = n.get_all_disrupt_methods()
    while list_disruptions:
        next_disrupt = list_disruptions.pop()
        print(next_disrupt)
        n.execute_disrupt_method(disrupt_method=next_disrupt)


