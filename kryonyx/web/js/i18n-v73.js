/* v73 strings: search layout, button sweep fixes and player additions.
   Source keys are English. Fill-only: an existing translation is never
   replaced. Russian and Ukrainian are complete. */
'use strict';
(() => {
 const fill = (code, pack) => { const target = typeof PACKS !== 'undefined' ? PACKS[code] : null; if (!target) return; for (const [k, v] of Object.entries(pack)) if (!(k in target)) target[k] = v; };
 fill('ru', {
  'The video was stuttering, so the background effects were made lighter.': 'Видео подтормаживало, поэтому фоновые эффекты стали легче.',
  'Click to undo.': 'Нажмите, чтобы вернуть.',
  'Show all tracks': 'Показать все треки',
  'Wave chooses what plays next. Click here to turn Wave off and use repeat.': 'Волна сама выбирает, что играть дальше. Нажмите сюда, чтобы выключить Волну и включить повтор.',
  'Wave chooses what plays next. Click here to turn Wave off and use shuffle.': 'Волна сама выбирает, что играть дальше. Нажмите сюда, чтобы выключить Волну и включить перемешивание.',
  'Wave controls the order. Turn Wave off to use this.': 'Волна управляет порядком. Выключите её, чтобы изменить режим.',
 });
 fill('uk', {
  'The video was stuttering, so the background effects were made lighter.': 'Відео пригальмовувало, тому фонові ефекти стали легшими.',
  'Click to undo.': 'Натисніть, щоб повернути.',
  'Show all tracks': 'Показати всі треки',
  'Wave chooses what plays next. Click here to turn Wave off and use repeat.': 'Хвиля сама обирає, що грати далі. Натисніть тут, щоб вимкнути Хвилю й увімкнути повтор.',
  'Wave chooses what plays next. Click here to turn Wave off and use shuffle.': 'Хвиля сама обирає, що грати далі. Натисніть тут, щоб вимкнути Хвилю й увімкнути перемішування.',
  'Wave controls the order. Turn Wave off to use this.': 'Хвиля керує порядком. Вимкніть її, щоб змінити режим.',
 });
 fill('es', { 'Show all tracks': 'Mostrar todas las pistas' });
 fill('de', { 'Show all tracks': 'Alle Titel anzeigen' });
 fill('fr', { 'Show all tracks': 'Afficher tous les titres' });
 fill('it', { 'Show all tracks': 'Mostra tutti i brani' });
 fill('pt', { 'Show all tracks': 'Mostrar todas as faixas' });
 fill('tr', { 'Show all tracks': 'Tüm parçaları göster' });
 fill('pl', { 'Show all tracks': 'Pokaż wszystkie utwory' });
})();
