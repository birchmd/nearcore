import matplotlib.pyplot as plt
import sys

def read_columns(filename):
  x = []
  y = []
  z = []
  with open(filename) as f:
    for l in f.readlines():
      a, b, c = [float(c) for c in l.strip().split(',')]
      x.append(a)
      y.append(b)
      z.append(c)
  return (x, y, z)

def create_plot(x, y, z, num_shards, out_filename):
  plt.plot(x, y, label='sent')
  plt.plot(x, z, label='processed')
  plt.ylim(0, 1700)
  plt.xlim(0, 300)
  plt.xlabel('Time (seconds)')
  plt.ylabel('Transactions per second')
  plt.title(f'{num_shards} shards')
  plt.legend()
  plt.savefig(out_filename)

num_shards = sys.argv[1]
input_filename = f'throughput_results_{num_shards}shard_average.csv'
output_filename = f'throughput_{num_shards}shard.png'
x, y, z = read_columns(input_filename)
create_plot(x, y, z, num_shards, output_filename)
