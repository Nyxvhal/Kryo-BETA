"""Stage lightweight runtime artwork without changing originals or user files.
Run by PyInstaller spec. ICOs are generated lazily from bundled PNGs at runtime.
"""
from pathlib import Path
import json,shutil
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]

def prepare(destination=None):
    dest=Path(destination or ROOT/'build/runtime-assets')
    if dest.exists():shutil.rmtree(dest)
    dest.mkdir(parents=True)
    web=ROOT/'kryonyx/web';target=dest/'web';shutil.copytree(web,target,ignore=shutil.ignore_patterns('harness.html','taskbar.html','__pycache__','*.map'))
    before=sum(p.stat().st_size for p in web.rglob('*') if p.is_file());changed=0
    # 512 px stays crisp at 2× the normal avatar UI size; PNG remains PNG.
    for path in (target/'img/avatars').glob('*.png'):
        with Image.open(path) as im:
            if max(im.size)>512:
                im.thumbnail((512,512),Image.Resampling.LANCZOS);im.save(path,format='PNG',optimize=True);changed+=1
    icons=dest/'icons';icons.mkdir()
    for aid in ['kryonyx-02-black-violet','kryonyx-01-sky']:
        source=ROOT/'kryonyx/icons'/f'{aid}.ico'
        if source.exists():shutil.copy2(source,icons/source.name)
    media=ROOT/'kryonyx/icons/media'
    if media.exists():shutil.copytree(media,icons/'media')
    after=sum(p.stat().st_size for p in target.rglob('*') if p.is_file())
    old_icons=sum(p.stat().st_size for p in (ROOT/'kryonyx/icons').rglob('*') if p.is_file())
    new_icons=sum(p.stat().st_size for p in icons.rglob('*') if p.is_file())
    report={'web_before_bytes':before,'web_after_bytes':after,'icons_before_bytes':old_icons,'icons_after_bytes':new_icons,'runtime_asset_bytes_saved':before+old_icons-after-new_icons,'resized_pngs':changed,'note':'Raw runtime assets only; not the measured size of a Windows setup EXE.'}
    (dest/'SIZE_REPORT.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return dest,report
if __name__=='__main__':print(json.dumps(prepare()[1],indent=2))
