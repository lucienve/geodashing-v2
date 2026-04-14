import os

def process_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if 'declare(strict_types=1);' in content:
        return
    
    if content.startswith('<?php'):
        # Add strict types right after the PHP open tag
        content = content.replace('<?php', '<?php\n\ndeclare(strict_types=1);', 1)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

directory = 'backend/'

for root, dirs, files in os.walk(directory):
    for filename in files:
        if filename.endswith('.php'):
            process_file(os.path.join(root, filename))

print("Completed strict_types insertion.")
