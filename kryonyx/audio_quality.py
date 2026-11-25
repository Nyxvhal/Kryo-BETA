"""Source quality preferences; never upsample or claim unavailable lossless."""
def mode():
    try:
        from . import storage
        value=storage.get_settings().get('audioQuality','best')
    except Exception:value='best'
    return value if value in ('best','balanced','data') else 'best'

def pick(items, bitrate):
    ordered=sorted(items,key=lambda x:float(bitrate(x) or 0))
    if not ordered:return None
    cap={'balanced':160_000,'data':80_000}.get(mode())
    pool=[x for x in ordered if 0<float(bitrate(x) or 0)<=cap] if cap else ordered
    return (pool or ordered[:1])[-1]

def format_selector():
    cap={'balanced':160,'data':80}.get(mode())
    return f'bestaudio[abr<={cap}]/worstaudio/bestaudio' if cap else 'bestaudio/best'
