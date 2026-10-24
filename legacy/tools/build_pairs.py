"""Write numbered EN/HE paragraph pairs (+ term table) per chunk for reviewers."""
import re, subprocess, sys
from pathlib import Path
TB = Path(__file__).resolve().parent.parent / "translate-book"  # the app's copy
T, R = Path(sys.argv[1]), Path(sys.argv[2]); R.mkdir(parents=True, exist_ok=True)
paras = lambda p: [x.strip() for x in re.split(r'\n\s*\n', p.read_text(encoding='utf-8')) if x.strip()]
for i in sys.argv[3:]:
    en, he = paras(T / f'chunk{i}.md'), paras(T / f'output_chunk{i}.md'); assert len(en) == len(he), (i, len(en), len(he))
    terms = subprocess.run([sys.executable, str(TB / 'scripts/glossary.py'), 'print-terms-for-chunk', str(T), f'chunk{i}.md'], capture_output=True, text=True).stdout.strip()
    out = [f'# Chunk {i} — {len(en)} paragraphs\n\n## Required terms\n\n{terms}\n\n## Paragraphs\n'] + [f'### P{n}\n\nEN:\n{e}\n\nHE:\n{h}\n' for n, (e, h) in enumerate(zip(en, he), 1)]
    (R / f'pairs_{i}.md').write_text('\n'.join(out), encoding='utf-8')
print('pairs written for', sys.argv[3:])
