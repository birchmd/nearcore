def map_line(s):
    needle = 'part: ['
    index = s.find(needle)
    while index != -1:
        index += len(needle)
        end_index = s.find(']', index)
        s = s[:index] + '...' + s[end_index:]
        index = s.find(needle, index + 1)
    return s

def condense_logs(input, output):
    with open(input) as log_file:
        with open(output, 'w') as dest_file:
            for line in log_file:
                dest_file.write(map_line(line))

condense_logs('near.log', 'near_condensed.log')
