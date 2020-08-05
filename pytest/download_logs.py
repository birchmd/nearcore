import sys
from rc import bash

sys.path.append('lib')
import mocknet

bash('rm ./logs/*')
nodes = mocknet.get_nodes()
mocknet.get_logs(nodes)
