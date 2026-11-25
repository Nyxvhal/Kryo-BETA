"""Bounded, allowlisted music metadata import. Never extracts archives to disk.
No credentials, account identity, cookies, device data or raw event times are stored.
"""
from __future__ import annotations
import csv,hashlib,io,json,math,re,secrets,stat,threading,time,zipfile,zlib
from pathlib import PurePosixPath
from . import playlist_transfer as portable,storage
from .trackmeta import clean_track
MAX_UPLOAD=8*1024*1024
MAX_EXPANDED=32*1024*1024
MAX_FILES=128
MAX_ROWS=25000
MAX_TRACKS=5000
SERVICES=portable.SERVICES
_lock=threading.RLock()
_staged={}

def norm(s):return ''.join(c for c in str(s or '').casefold() if c.isalnum())
def _text(s):return s.strip()[:300] if isinstance(s,str) else ''
def _track(row):
 if not isinstance(row,dict):return None
 if isinstance(row.get('track'),dict):row=row['track']
 title=row.get('master_metadata_track_name') or row.get('trackName') or row.get('track_name') or (row.get('track') if isinstance(row.get('track'),str) else '')
 artist=row.get('master_metadata_album_artist_name') or row.get('artistName') or row.get('artist_name')
 if title:row={**row,'title':title,'artist':artist or row.get('artist','')}
 item=portable._track(row)
 if item:item=clean_track(item)
 if not item:return None
 # Keep only musical metadata. Exported paths/URLs/accounts are intentionally discarded.
 return {'title':item['title'][:300],'artist':item['artist'][:300]}
def _count(value):
 try:return min(100,max(1,int(float(value))))
 except (ValueError,TypeError,OverflowError):return 1

def parse(raw:bytes,filename:str,service:str)->dict:
 if service not in SERVICES:raise ValueError('Unknown music service')
 if not isinstance(raw,bytes) or not raw or len(raw)>MAX_UPLOAD:raise ValueError('Choose a non-empty file up to 8 MB')
 files=[];ignored=0
 if raw.startswith(b'PK'):
  try:
   with zipfile.ZipFile(io.BytesIO(raw)) as z:
    entries=z.infolist()
    if len(entries)>MAX_FILES:raise ValueError('Archive has more than 128 entries; select music files only')
    if sum(x.file_size for x in entries)>MAX_EXPANDED:raise ValueError('Expanded archive exceeds 32 MB; split the export')
    for x in entries:
     path=PurePosixPath(x.filename.replace('\\','/'))
     if path.is_absolute() or '..' in path.parts or stat.S_ISLNK(x.external_attr>>16):raise ValueError('Unsafe archive entry')
     if x.flag_bits&1:raise ValueError('Encrypted archives are not supported')
     if x.is_dir():continue
     if x.file_size>MAX_EXPANDED or x.file_size/max(1,x.compress_size)>200:raise ValueError('Archive compression ratio is unsafe; select individual files')
     if path.suffix.lower() not in {'.json','.csv','.tsv','.xml','.m3u','.m3u8'}:ignored+=1;continue
     data=z.read(x)
     if len(data)!=x.file_size:raise ValueError('Invalid archive entry size')
     files.append((path.name,data))
  except (zipfile.BadZipFile,RuntimeError,NotImplementedError,OSError,EOFError,zlib.error) as exc:raise ValueError('Cannot read archive; choose JSON or CSV files instead') from exc
 else:files=[(PurePosixPath(filename.replace('\\','/')).name,raw)]
 buckets={'favorites':{},'history':{},'playlists':{}};artists={};rows=0;duplicates=0;skipped=0;recognized=0
 def add(category,row,count=1):
  nonlocal rows,duplicates,skipped
  rows+=1
  if rows>MAX_ROWS:raise ValueError('Maximum 25000 records per import; split the export')
  item=_track(row)
  if not item:skipped+=1;return
  key=(norm(item['artist']),norm(item['title']))
  dest=buckets[category]
  if key in dest:
   duplicates+=1
   if category=='history':dest[key]['count']=min(100,dest[key].get('count',1)+_count(count))
   return
  if sum(map(len,buckets.values()))>=MAX_TRACKS:raise ValueError('Maximum 5000 unique music records; split the export')
  if category=='history':item['count']=_count(count)
  dest[key]=item
 def artist(value):
  nonlocal rows
  rows+=1
  if rows>MAX_ROWS:raise ValueError('Maximum 25000 records per import; split the export')
  name=_text(value.get('name') or value.get('artist')) if isinstance(value,dict) else _text(value)
  if name and len(artists)<500:artists[norm(name)]={'artist':name}
 def sequence(value):
  if isinstance(value,dict):value=value.get('items',value.get('data',[]))
  return value if isinstance(value,list) else []
 for name,data in files:
  try:text=data.decode('utf-8-sig').strip()
  except UnicodeDecodeError:ignored+=1;continue
  if not text:continue
  before=rows
  if text.startswith(('{','[')):
   try:doc=json.loads(text)
   except (ValueError,RecursionError) as exc:raise ValueError('Invalid JSON in music export') from exc
   if isinstance(doc,dict) and isinstance(doc.get('response'),dict):doc=doc['response']
   if isinstance(doc,dict):
    for key in ('favorites','liked_tracks','likedTracks','saved_tracks','tracks','songs','audios'):
     for row in sequence(doc.get(key)):add('favorites',row)
    for key in ('history','streamingHistory','recentlyPlayed'):
     for row in sequence(doc.get(key)):add('history',row,row.get('count',row.get('playCount',1)) if isinstance(row,dict) else 1)
    for row in sequence(doc.get('artists')):artist(row)
    for pl in sequence(doc.get('playlists')):
     if isinstance(pl,dict):
      for row in sequence(pl.get('items',pl.get('tracks',[]))):add('playlists',row)
    if not rows-before:
     for row in sequence(doc.get('items')):add('favorites',row)
   elif isinstance(doc,list):
    for row in doc:
     if not isinstance(row,dict):skipped+=1;continue
     if 'master_metadata_track_name' in row:
      if row.get('master_metadata_track_name') and isinstance(row.get('ms_played'),(int,float)) and row['ms_played']>=30000:add('history',row)
      else:skipped+=1
     elif 'msPlayed' in row or 'endTime' in row:
      if _count(row.get('msPlayed',30000)) and (isinstance(row.get('msPlayed',30000),(int,float)) and row.get('msPlayed',30000)>=30000):add('history',row)
      else:skipped+=1
     elif 'subtitles' in row and 'title' in row:
      # Ordinary YouTube watch history can include arbitrary non-music videos.
      products=row.get('products');products=products if isinstance(products,list) else []
      music=row.get('header')=='YouTube Music' or 'YouTube Music' in products
      subs=row.get('subtitles');subs=subs if isinstance(subs,list) else []
      a=_text(subs[0].get('name')) if subs and isinstance(subs[0],dict) else ''
      title=re.sub(r'^(Watched |Просмотрено видео |Просмотрено: )','',str(row['title']))
      if music:add('history',{'title':title,'artist':re.sub(r' - Topic$','',a)})
      else:skipped+=1
     else:add('history' if 'history' in name.lower() else 'favorites',row,row.get('count',1))
  elif PurePosixPath(name).suffix.lower() in {'.csv','.tsv'}:
   try:dialect=csv.Sniffer().sniff(text[:8192],delimiters=',;\t')
   except csv.Error:dialect=csv.excel_tab if '\t' in text.splitlines()[0] else csv.excel
   try:
    for row in csv.DictReader(io.StringIO(text),dialect=dialect):
     count=row.get('Play Count',row.get('playCount',row.get('count',1)))
     add('history' if 'history' in name.lower() or 'Play Count' in row or 'playCount' in row else 'favorites',row,count)
   except csv.Error as exc:raise ValueError('Invalid CSV in music export') from exc
  elif text.startswith(('<?xml','<plist','#EXTM3U')):
   if len(data)>portable.MAX_BYTES:raise ValueError('XML/M3U playlist exceeds 2 MB')
   for row in portable.parse(text,name,service)['items']:add('playlists',row)
  else:ignored+=1
  if rows>before:recognized+=1
  else:ignored+=1
 if not any(buckets.values()) and not artists:raise ValueError('No supported music data found. Use Spotify music history/library JSON, YouTube Music history JSON, music CSV or the profile template')
 return {'service':service,**{key:list(value.values()) for key,value in buckets.items()},'artists':list(artists.values()),'ignored_files':ignored,'recognized_files':recognized,'duplicates':duplicates,'skipped':skipped}

def stage(raw,filename,service):
 data=parse(raw,filename,service);now=time.monotonic()
 with _lock:
  for key in list(_staged):
   if _staged[key][0]<now:_staged.pop(key,None)
  while len(_staged)>=8:_staged.pop(next(iter(_staged)))
  token=secrets.token_urlsafe(24);_staged[token]=(now+600,data)
 return {'token':token,'service':service,'counts':{k:len(data[k]) for k in ('favorites','history','artists','playlists')},'sample':(data['favorites']+data['history']+data['playlists'])[:8],'ignored_files':data['ignored_files'],'skipped':data['skipped'],'duplicates':data['duplicates'],'expires_in':600}

def _schema():
 storage._conn().execute('CREATE TABLE IF NOT EXISTS imported_taste(service TEXT PRIMARY KEY,payload TEXT NOT NULL,updated_at REAL NOT NULL)')
def profiles():
 _schema();return [json.loads(x['payload']) for x in storage._conn().execute('SELECT payload FROM imported_taste ORDER BY updated_at DESC')]
def summary():
 return [{'service':p['service'],'counts':{k:len(p[k]) for k in ('favorites','history','artists','playlists')},'updated_at':p['updated_at'],'artists':list(dict.fromkeys([x['artist'] for x in p['artists']+p['favorites']+p['history'] if x.get('artist')]))[:8]} for p in profiles()]
def apply(token,selected):
 global _context_cache
 if not isinstance(token,str) or not isinstance(selected,list) or not selected or any(not isinstance(x,str) or x not in {'favorites','history','artists','playlists'} for x in selected):raise ValueError('Choose at least one music-data category')
 with _lock:
  hit=_staged.get(token)
  if not hit or hit[0]<time.monotonic():raise ValueError('Preview expired. Choose the file again')
  data=hit[1];profile={'service':data['service'],**{k:data[k] if k in selected else [] for k in ('favorites','history','artists','playlists')}}
  if not any(profile[k] for k in selected):raise ValueError('The selected categories contain no music data')
  fingerprint=hashlib.sha256(json.dumps(profile,sort_keys=True,ensure_ascii=False).encode()).hexdigest();_schema();conn=storage._conn()
  previous=conn.execute('SELECT payload FROM imported_taste WHERE service=?',(data['service'],)).fetchone()
  if previous and json.loads(previous['payload']).get('fingerprint')==fingerprint:return {'unchanged':True,'profiles':summary()}
  profile.update(fingerprint=fingerprint,updated_at=time.time())
  _context_cache=None
  with conn:conn.execute('INSERT OR REPLACE INTO imported_taste VALUES(?,?,?)',(data['service'],json.dumps(profile,ensure_ascii=False),time.time()))
 return {'unchanged':False,'profiles':summary()}
def remove(service):
 global _context_cache
 _context_cache=None
 if service not in SERVICES:raise ValueError('Unknown music service')
 _schema();conn=storage._conn()
 with conn:conn.execute('DELETE FROM imported_taste WHERE service=?',(service,))
_context_cache = None

def signatures():
 _schema()
 return [(x['service'],x['updated_at']) for x in storage._conn().execute('SELECT service,updated_at FROM imported_taste ORDER BY service')]

def context():
 global _context_cache
 signature=(storage._db_path,tuple(signatures()))
 if _context_cache and _context_cache[0]==signature:return _context_cache[1]
 value=_build_context();_context_cache=(signature,value);return value

def _build_context():
 """Bounded external signals kept separate from genuine local listen statistics."""
 weights={};names={};played=set();liked=set();queries=[]
 for p in profiles():
  for row in p['artists']:
   k=norm(row['artist']);names[k]=row['artist'];weights[k]=weights.get(k,0)+3
  for row in (p['favorites']+p['history'])[:4]:
   query=(row.get('artist','')+' '+row['title']).strip()
   if query and query not in queries:queries.append(query[:500])
  for category in ('favorites','history','playlists'):
   for row in p[category]:
    key=(norm(row['artist']),norm(row['title']))
    if category=='history':played.add(key)
    elif category=='favorites':liked.add(key)
    if key[0]:
     names[key[0]]=row['artist'];weights[key[0]]=weights.get(key[0],0)+(2 if category=='favorites' else .3 if category=='playlists' else min(3,math.log1p(row.get('count',1))))
 return {'artists':[{'artist':names[k],'weight':min(30,v)} for k,v in sorted(weights.items(),key=lambda x:-x[1])[:200]],'played':played,'liked':liked,'queries':queries[:4]}
