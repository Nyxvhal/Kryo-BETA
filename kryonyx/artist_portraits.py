"""Read only real profile artwork. Never substitute an album/video cover."""
import asyncio,json,re
from . import ytmusic
from .trackmeta import artist_name_key,artist_profile_key

async def portrait(name,url=None,source=None):
    profile=artist_profile_key(url)
    mismatched=False
    if profile and profile[0]=='youtube-channel':
        try:
            data=await asyncio.wait_for(ytmusic._call('get_artist',profile[1]),6)
            identity=(data or {}).get('name') or (data or {}).get('title')
            mismatched=bool(identity and name and artist_name_key(identity)!=artist_name_key(name))
            image=None if mismatched else ytmusic._thumb(data or {})
            if image:return {'picture':image,'picture_source':url}
        except Exception:pass
    if profile and profile[0]=='soundcloud':
        try:
            from . import youtube
            session=await youtube.http()
            async with session.get('https://soundcloud.com/'+profile[1],allow_redirects=False) as response:
                if response.status==200:
                    html=(await response.content.read(2*1024*1024)).decode('utf-8','replace')
                    match=re.search(r'window\.__sc_hydration\s*=\s*(\[.*?\]);',html,re.S)
                    for record in json.loads(match.group(1)) if match else []:
                        user=record.get('data') or {}
                        if record.get('hydratable')=='user' and user.get('avatar_url'):
                            return {'picture':user['avatar_url'],'picture_source':url}
        except Exception:pass
    if source in (None,'youtube') and name:
        try:
            found=await asyncio.wait_for(ytmusic.artists(name,8),5)
            match=next((a for a in found if (profile and not mismatched and artist_profile_key(a.get('url'))==profile) or ((not url or mismatched) and artist_name_key(a.get('name'))==artist_name_key(name))),None)
            if match and match.get('thumbnail'):return {'picture':match['thumbnail'],'picture_source':match.get('url')}
        except Exception:pass
    return {}
