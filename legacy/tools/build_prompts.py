"""Build per-chunk translation prompts from translate-book's SKILL.md template.
Usage: python build_prompts.py <temp_dir> <out_dir> [first last]
The brief is tools/custom_instructions.txt, or the file named by the BRIEF environment variable."""
import re, subprocess, sys, os, glob
from pathlib import Path
TB = Path(__file__).resolve().parent.parent / "translate-book"  # the app's copy
T, out = sys.argv[1], sys.argv[2]; os.makedirs(out, exist_ok=True)
n = len(glob.glob(f'{T}/chunk[0-9]*.md'))
first, last = (int(sys.argv[3]), int(sys.argv[4])) if len(sys.argv) > 4 else (1, n)
skill = open(str(TB / 'SKILL.md'), encoding='utf-8').read()
end_marker = 'The full contents of your assigned chunk file follow.'
tmpl = skill[skill.index('You are an expert literary translator.'):skill.index(end_marker)+len(end_marker)]
meta = skill[skill.index('**Sub-agent meta schema**'):skill.index('**IMPORTANT**: Each sub-agent translates exactly ONE chunk')].strip()
custom = open(os.environ.get('BRIEF') or os.path.join(os.path.dirname(__file__), 'custom_instructions.txt'), encoding='utf-8').read().strip()
def section(text, heading, keep):
    m = re.compile(r'## ' + re.escape(heading) + r'.*?(?=\n## )', re.S).search(text); assert m, heading
    if not keep: return text[:m.start()] + text[m.end()+1:]
    return text[:m.start()] + re.sub(r' \*\(conditional:[^)]*\)\*', '', m.group(0), count=1) + text[m.end():]
for i in range(first, last+1):
    c = f'chunk{i:04d}.md'
    terms = subprocess.run([sys.executable,str(TB / 'scripts/glossary.py'),'print-terms-for-chunk',T,c],capture_output=True,text=True).stdout.strip()
    ctx = subprocess.run([sys.executable,str(TB / 'scripts/chunk_context.py'),T,c],capture_output=True,text=True).stdout.strip()
    p = tmpl.replace('{TARGET_LANGUAGE}', 'Hebrew')
    p = section(p, 'Terminology', bool(terms)).replace('{TERM_TABLE}', terms)
    p = section(p, 'Hebrew conventions', True)
    p = section(p, 'Torah-scholarship register', False)
    p = section(p, 'Custom instructions', True).replace('{CUSTOM_INSTRUCTIONS}', custom)
    p = section(p, 'Neighbor context', bool(ctx)).replace('{NEIGHBOR_CONTEXT}', ctx)
    open(os.path.join(out, f'prompt_{i:04d}.md'), 'w', encoding='utf-8').write(p + '\n\n---\n\n' + meta + '\n')
print(f'prompts {first}-{last} written ({n} chunks)')
