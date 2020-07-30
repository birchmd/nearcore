# Checks that a network is still able to operate when some fraction of messages
# are randomly dropped.

import sys, time
from rc import pmap

from messages_dropped_helper import TEST_DURATION
from load_testing import check_stats

sys.path.append('lib')
import mocknet

if __name__ == '__main__':
    nodes = mocknet.get_nodes(prefix='sharded-')
    mocknet.setup_python_environments(nodes, ['tests/mocknet/messages_dropped_helper.py', 'tests/mocknet/load_testing_helper.py'])
    # stop currently running nodes to replace them with proxied ones
    pmap(mocknet.stop_node, nodes)
    # start proxied nodes
    mocknet.start_load_test_helpers(nodes, 'messages_dropped_helper.py')
    # Give some time for the nodes to boot up
    time.sleep(30)

    test_passing = True
    start_time = time.time()
    while time.time() - start_time < TEST_DURATION:
        try:
            check_stats(query_node=nodes[-1], duration=30, target_tps=75)
        except AssertionError:
            # If the check fails we do not fail the test immediately, we wait for it
            # to finish so we can clean up.
            test_passing = False
        except Exception as err:
            print(f'ERROR: Error during tps measurement: {err}')

    # wait a moment to ensure all nodes have completed
    time.sleep(10)
    # restart unproxied nodes
    pmap(mocknet.start_node, nodes)
    # Give some time for the nodes to boot up
    time.sleep(30)

    # fail the test, if necessary
    assert test_passing
