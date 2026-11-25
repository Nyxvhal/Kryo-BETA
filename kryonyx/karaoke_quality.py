"""Conservative diagnostics. Confidence is NOT a guarantee of lyric accuracy."""
from __future__ import annotations
import re
import unicodedata

def canonical(text):
    return ''.join(c for c in unicodedata.normalize('NFKC', text).casefold() if c.isalnum())

def reference_matches(document, reference):
    return canonical(''.join(w['text'] for l in document['lines'] for w in l.get('words', []))) == canonical(reference)

def assess(document):
    words = [w for l in document.get('lines', []) for w in l.get('words', [])]
    alignment = document.get('alignment') or {}
    warnings = []
    def warn(code):
        if code not in warnings: warnings.append(code)
    if alignment.get('engine') in ('faster-whisper', 'stable-ts') and not alignment.get('forced'):
        warn('asr_draft')
    if alignment.get('model') in ('tiny', 'base'): warn('light_model')
    if alignment.get('refinement') in ('failed','unavailable'): warn('refinement_skipped')
    if words: warn('timing_estimated')
    else: warn('line_only')
    confidences = [w['confidence'] for w in words if isinstance(w.get('confidence'), (float, int))]
    low = sum(c < .6 for c in confidences)
    if low: warn('low_confidence')
    if any(w['end']-w['start'] < .035 for w in words): warn('short_words')
    if any(w['end']-w['start'] > 3.5 for w in words): warn('long_words')
    if any(canonical(words[i]['text']) and len({canonical(w['text']) for w in words[i:i+5]}) == 1
           for i in range(max(0, len(words)-4))): warn('repetition')
    duration = document.get('duration')
    if isinstance(duration, (int, float)) and duration > 0:
        if any(l['end'] > duration+.1 for l in document.get('lines', [])): warn('outside_audio')
    if any(l.get('words') and canonical(l.get('text','')) != canonical(''.join(w['text'] for w in l['words'])) for l in document.get('lines', [])):
        warn('partial_word_text')
    old = document.get('quality') or {}
    reviewed = old.get('reviewed') is True
    # Acknowledging review is a human decision, never a confidence threshold.
    return {'status':'reviewed' if reviewed else 'needs_review', 'reviewed':reviewed,
            'warnings':warnings, 'word_count':len(words), 'low_confidence_words':low,
            'confidence_available':len(confidences), 'reference_provided':bool(alignment.get('forced')),
            'syllables_provided':any(w.get('syllables') for w in words),
            'notice':'Diagnostics do not measure acoustic accuracy. Verify against this recording.'}

def readable_segments(segments, max_words=9, max_chars=64):
    """Break ASR paragraphs into readable rows without inventing/re-timing words."""
    out=[]
    for segment in segments:
        group=[]
        for word in segment.get('words', []):
            if group and (len(group)>=max_words or len(''.join(w.get('word',w.get('text','')) for w in group))+len(word.get('word',word.get('text','')))>max_chars
                          or float(word['start'])-float(group[-1]['end'])>.85):
                out.append({'words':group});group=[]
            group.append(word)
        if group: out.append({'words':group})
    return out
