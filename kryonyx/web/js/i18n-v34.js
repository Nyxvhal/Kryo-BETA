'use strict';
for(const [lang,values] of Object.entries({
  "ru": {
    "Lyrics & artwork": "Текст и обложка",
    "Player mode": "Режим плеера",
    "A track list is required": "Нужен список треков",
    "The source returned only part of this playlist. Some tracks may be unavailable.": "Источник вернул только часть плейлиста. Некоторые треки могут быть недоступны."
  },
  "es": {
    "Lyrics & artwork": "Letra y portada",
    "Player mode": "Modo del reproductor",
    "A track list is required": "Se necesita una lista de pistas",
    "The source returned only part of this playlist. Some tracks may be unavailable.": "La fuente solo devolvió parte de la lista. Algunas pistas pueden no estar disponibles."
  },
  "pt": {
    "Lyrics & artwork": "Letra e capa",
    "Player mode": "Modo do leitor",
    "A track list is required": "É necessária uma lista de faixas",
    "The source returned only part of this playlist. Some tracks may be unavailable.": "A fonte devolveu apenas parte da lista. Algumas faixas podem estar indisponíveis."
  },
  "de": {
    "Lyrics & artwork": "Liedtext und Cover",
    "Player mode": "Wiedergabemodus",
    "A track list is required": "Eine Titelliste ist erforderlich",
    "The source returned only part of this playlist. Some tracks may be unavailable.": "Die Quelle hat nur einen Teil der Wiedergabeliste geliefert. Einige Titel sind möglicherweise nicht verfügbar."
  },
  "fr": {
    "Lyrics & artwork": "Paroles et pochette",
    "Player mode": "Mode du lecteur",
    "A track list is required": "Une liste de titres est requise",
    "The source returned only part of this playlist. Some tracks may be unavailable.": "La source n’a renvoyé qu’une partie de la playlist. Certains titres peuvent être indisponibles."
  },
  "it": {
    "Lyrics & artwork": "Testo e copertina",
    "Player mode": "Modalità del lettore",
    "A track list is required": "È necessario un elenco di brani",
    "The source returned only part of this playlist. Some tracks may be unavailable.": "La fonte ha restituito solo parte della playlist. Alcuni brani potrebbero non essere disponibili."
  },
  "tr": {
    "Lyrics & artwork": "Şarkı sözleri ve kapak",
    "Player mode": "Oynatıcı modu",
    "A track list is required": "Bir parça listesi gerekli",
    "The source returned only part of this playlist. Some tracks may be unavailable.": "Kaynak çalma listesinin yalnızca bir bölümünü döndürdü. Bazı parçalar kullanılamıyor olabilir."
  },
  "pl": {
    "Lyrics & artwork": "Tekst i okładka",
    "Player mode": "Tryb odtwarzacza",
    "A track list is required": "Wymagana jest lista utworów",
    "The source returned only part of this playlist. Some tracks may be unavailable.": "Źródło zwróciło tylko część playlisty. Niektóre utwory mogą być niedostępne."
  },
  "uk": {
    "Lyrics & artwork": "Текст і обкладинка",
    "Player mode": "Режим плеєра",
    "A track list is required": "Потрібен список треків",
    "The source returned only part of this playlist. Some tracks may be unavailable.": "Джерело повернуло лише частину плейлиста. Деякі треки можуть бути недоступні."
  },
  "zh": {
    "Lyrics & artwork": "歌词与封面",
    "Player mode": "播放器模式",
    "A track list is required": "需要曲目列表",
    "The source returned only part of this playlist. Some tracks may be unavailable.": "来源仅返回了播放列表的一部分。部分曲目可能无法获取。"
  },
  "ja": {
    "Lyrics & artwork": "歌詞とアートワーク",
    "Player mode": "プレーヤーモード",
    "A track list is required": "曲のリストが必要です",
    "The source returned only part of this playlist. Some tracks may be unavailable.": "配信元からプレイリストの一部のみが返されました。一部の曲は利用できない可能性があります。"
  }
}))Object.assign(PACKS[lang],values);
