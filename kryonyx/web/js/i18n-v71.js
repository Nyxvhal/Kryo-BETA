/* v71 strings: clip room «Cinema» and viewing mode. Source keys are English.
   Fill-only: an existing translation is never replaced. */
'use strict';
(() => {
 const fill = (code, pack) => { const target = PACKS[code]; if (!target) return; for (const [k, v] of Object.entries(pack)) if (!(k in target)) target[k] = v; };
 const keys = ['All videos', 'Viewing mode', 'Viewing mode (T)', 'Exit viewing mode (T)', 'Exit viewing mode', 'More from the artist', 'Autoplay', 'Video size', 'Viewing mode · T or Esc to exit', 'Now playing', 'Close', 'Download', 'Moving blurred background', 'Blur', 'Dim'];
 const rows = {
  ru: ['Все клипы', 'Режим просмотра', 'Режим просмотра (T)', 'Выйти из режима просмотра (T)', 'Выйти из режима просмотра', 'Ещё от исполнителя', 'Автовоспроизведение', 'Размер видео', 'Режим просмотра · выход — T или Esc', 'Сейчас играет', 'Закрыть', 'Скачать', 'Размытый фон из видео', 'Размытие', 'Затемнение'],
  uk: ['Усі кліпи', 'Режим перегляду', 'Режим перегляду (T)', 'Вийти з режиму перегляду (T)', 'Вийти з режиму перегляду', 'Більше від виконавця', 'Автовідтворення', 'Розмір відео', 'Режим перегляду · вихід — T або Esc', 'Зараз грає', 'Закрити', 'Завантажити', 'Розмите тло з відео', 'Розмиття', 'Затемнення'],
  es: ['Todos los vídeos', 'Modo de visualización', 'Modo de visualización (T)', 'Salir del modo de visualización (T)', 'Salir del modo de visualización', 'Más del artista', 'Reproducción automática', 'Tamaño del vídeo', 'Modo de visualización · T o Esc para salir', 'Reproduciendo', 'Cerrar', 'Descargar', 'Fondo difuminado del vídeo', 'Desenfoque', 'Oscurecer'],
  pt: ['Todos os vídeos', 'Modo de visualização', 'Modo de visualização (T)', 'Sair do modo de visualização (T)', 'Sair do modo de visualização', 'Mais do artista', 'Reprodução automática', 'Tamanho do vídeo', 'Modo de visualização · T ou Esc para sair', 'Tocando agora', 'Fechar', 'Baixar', 'Fundo desfocado do vídeo', 'Desfoque', 'Escurecer'],
  de: ['Alle Videos', 'Fokusmodus', 'Fokusmodus (T)', 'Fokusmodus beenden (T)', 'Fokusmodus beenden', 'Mehr vom Künstler', 'Autoplay', 'Videogröße', 'Fokusmodus · T oder Esc zum Beenden', 'Läuft gerade', 'Schließen', 'Herunterladen', 'Unscharfer Hintergrund aus dem Video', 'Unschärfe', 'Abdunkeln'],
  fr: ['Toutes les vidéos', 'Mode visionnage', 'Mode visionnage (T)', 'Quitter le mode visionnage (T)', 'Quitter le mode visionnage', 'Plus de cet artiste', 'Lecture automatique', 'Taille de la vidéo', 'Mode visionnage · T ou Échap pour quitter', 'En cours de lecture', 'Fermer', 'Télécharger', 'Arrière-plan flou de la vidéo', 'Flou', 'Assombrir'],
  it: ['Tutti i video', 'Modalità visione', 'Modalità visione (T)', 'Esci dalla modalità visione (T)', 'Esci dalla modalità visione', 'Altro dall’artista', 'Riproduzione automatica', 'Dimensione video', 'Modalità visione · T o Esc per uscire', 'In riproduzione', 'Chiudi', 'Scarica', 'Sfondo sfocato dal video', 'Sfocatura', 'Oscuramento'],
  tr: ['Tüm videolar', 'İzleme modu', 'İzleme modu (T)', 'İzleme modundan çık (T)', 'İzleme modundan çık', 'Sanatçıdan daha fazlası', 'Otomatik oynatma', 'Video boyutu', 'İzleme modu · çıkmak için T veya Esc', 'Şimdi çalıyor', 'Kapat', 'İndir', 'Videodan bulanık arka plan', 'Bulanıklık', 'Karartma'],
  pl: ['Wszystkie klipy', 'Tryb oglądania', 'Tryb oglądania (T)', 'Wyjdź z trybu oglądania (T)', 'Wyjdź z trybu oglądania', 'Więcej od wykonawcy', 'Autoodtwarzanie', 'Rozmiar wideo', 'Tryb oglądania · T lub Esc, aby wyjść', 'Teraz odtwarzane', 'Zamknij', 'Pobierz', 'Rozmyte tło z wideo', 'Rozmycie', 'Przyciemnienie'],
  zh: ['全部视频', '观影模式', '观影模式 (T)', '退出观影模式 (T)', '退出观影模式', '该艺人的更多作品', '自动播放', '视频大小', '观影模式 · 按 T 或 Esc 退出', '正在播放', '关闭', '下载', '视频模糊背景', '模糊', '调暗'],
  ja: ['すべての動画', '視聴モード', '視聴モード (T)', '視聴モードを終了 (T)', '視聴モードを終了', 'このアーティストの他の動画', '自動再生', '動画サイズ', '視聴モード · T または Esc で終了', '再生中', '閉じる', 'ダウンロード', '動画のぼかし背景', 'ぼかし', '暗さ']
 };
 for (const [code, values] of Object.entries(rows)) fill(code, Object.fromEntries(keys.map((k, i) => [k, values[i]])));
 const youtube = { ru: 'Открыть на YouTube', uk: 'Відкрити на YouTube', es: 'Abrir en YouTube', pt: 'Abrir no YouTube', de: 'Auf YouTube öffnen', fr: 'Ouvrir sur YouTube', it: 'Apri su YouTube', tr: 'YouTube’da aç', pl: 'Otwórz w YouTube', zh: '在 YouTube 上打开', ja: 'YouTube で開く' };
 for (const [code, value] of Object.entries(youtube)) fill(code, { 'Open on YouTube': value });
})();
