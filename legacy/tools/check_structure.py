"""Compare structure of translated chunks with their sources: markers, notes, headings, quotes, paragraphs, length."""
import re, sys
from pathlib import Path
T = Path(sys.argv[1]); ids = sys.argv[2:]
paras = lambda s: [p for p in re.split(r'\n\s*\n', s) if p.strip()]
ok_all = True
for i in ids:
    s = (T / f'chunk{i}.md').read_text(encoding='utf-8'); p = T / f'output_chunk{i}.md'
    if not p.exists(): print(i, 'MISSING OUTPUT'); ok_all = False; continue
    t = p.read_text(encoding='utf-8')
    checks = {
        'markers': (re.findall(r'\^(\d+)\^', s), re.findall(r'\^(\d+)\^', t)),
        'notes': (re.findall(r'(?m)^(\d+)\\\.', s), re.findall(r'(?m)^(\d+)\\?\.', t)),
        'headings': (len(re.findall(r'(?m)^#+ ', s)), len(re.findall(r'(?m)^#+ ', t))),
        'quote-lines': (len(re.findall(r'(?m)^>', s)), len(re.findall(r'(?m)^>', t))),
        'paras': (len(paras(s)), len(paras(t))),
    }
    bad = [k for k, (a, b) in checks.items() if a != b]
    ok_all &= not bad
    print(f"{i}: {'OK' if not bad else 'DIFF ' + ','.join(bad)}  ratio {len(t)/max(1,len(s)):.2f}  " +
          ' '.join(f"{k}={len(a) if isinstance(a,list) else a}/{len(b) if isinstance(b,list) else b}" for k,(a,b) in checks.items() if k in bad))
sys.exit(0 if ok_all else 1)
