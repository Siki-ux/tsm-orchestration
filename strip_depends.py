import sys

def process_compose(filepath):
    with open(filepath, 'r') as f:
        lines = f.readlines()

    out_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Check if this line is "init:" or "flyway:" inside a depends_on block
        # The typical indent is 6 spaces: "      init:"
        # and the next line is "        condition: ..."
        
        if line.startswith("      init:") or line.startswith("      flyway:"):
            # Skip this line and the condition line if it exists
            if i + 1 < len(lines) and "condition:" in lines[i+1]:
                i += 2
                continue
            elif i + 1 < len(lines) and lines[i+1].strip() == "":
                # maybe just one line if it didn't have condition
                i += 1
                continue
                
        # Also handle empty depends_on blocks if we removed everything inside them
        if line.startswith("    depends_on:"):
            # Check if the next lines are just the ones we are removing
            j = i + 1
            has_other_deps = False
            while j < len(lines) and lines[j].startswith("      "):
                if not (lines[j].startswith("      init:") or lines[j].startswith("      flyway:") or "condition" in lines[j]):
                    has_other_deps = True
                    break
                j += 1
                
            if not has_other_deps:
                # We can skip the depends_on: line too!
                # And advance i to j
                i = j
                continue

        out_lines.append(line)
        i += 1
        
    with open(filepath, 'w') as f:
        f.write("".join(out_lines))

if __name__ == '__main__':
    process_compose(sys.argv[1])
