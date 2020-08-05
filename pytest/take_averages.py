import sys

def parse_row(line):
  cells = line.strip().split(',')
  return [float(c) for c in cells]

def format_row(r):
  return ','.join(map(str, r))

def average(basename):
  filenames = [f'{basename}_{i + 1}.csv' for i in range(0, 10)]
  NUM_ROWS = 149
  NUM_COLUMNS = 3
  n = len(filenames)
  total_rows = [[0.0, 0.0, 0.0] for _ in range(NUM_ROWS)]
  for filename in filenames:
    with open(filename) as f:
      rows = [parse_row(l) for l in f.readlines()]
      for i in range(NUM_ROWS):
        for j in range(NUM_COLUMNS):
          total_rows[i][j] += rows[i][j]
  for i in range(NUM_ROWS):
    for j in range(NUM_COLUMNS):
      total_rows[i][j] /= n
  output_filename = f'{basename}_average.csv'
  with open(output_filename, 'w') as f:
    for r in total_rows:
      f.write(format_row(r) + '\n')

average(sys.argv[1])
