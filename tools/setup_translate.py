"""Online, explicit installation of one Argos model and its MiniSBD resources."""
import os
import sys
os.environ['ARGOS_CHUNK_TYPE'] = 'MINISBD'
os.environ['ARGOS_DEVICE_TYPE'] = 'cpu'
import argostranslate.package as package
import argostranslate.translate as translate
source = (sys.argv[1] if len(sys.argv)>1 else 'en').replace('zh-CN','zh')
target = (sys.argv[2] if len(sys.argv)>2 else 'ru').replace('zh-CN','zh')
if not source.isalpha() or not target.isalpha() or source == target:
    raise SystemExit('Usage: setup-translate [source-code] [target-code] (e.g. en ru)')
print('Updating the Argos package index; internet is required for this setup.', flush=True)
package.update_package_index()
match = next((p for p in package.get_available_packages() if p.from_code == source and p.to_code == target), None)
if match is None:
    raise SystemExit('No direct Argos model for %s -> %s; install a route via an intermediate language.' % (source,target))
print('Downloading model %s -> %s...' % (source,target), flush=True)
package.install_from_path(match.download())
print('Preparing MiniSBD resources; this may download additional files.', flush=True)
result = translate.translate('Hello world.', source, target)
if not result.strip(): raise SystemExit('Warm-up returned an empty translation')
print('Ready: %s -> %s. Translation runs offline after setup.' % (source,target))
