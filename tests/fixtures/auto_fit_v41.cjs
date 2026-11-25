// Frozen v41 algorithm: independent oracle for v42 off-thread search.
module.exports={AUTO_RANGE:20,AUTO_STEP:.1,AUTO_MIN:45,AUTO_MAX:150,AUTO_GAIN:.12,clock:t=>t,wrongRecord(){this.wrong42=true;},  autoFit(box) {
    const count = box.t.length;
    const span = box.t[count - 1] - box.t[0];
    if (span < this.AUTO_MIN) return;

    const range = this.approx ? 30 : this.AUTO_RANGE;
    const spans = this.voiceSpans();
    if (!spans.length) { box.done = true; return; }
    const covers = x => {
      let lo = 0, hi = spans.length - 1;
      while (lo <= hi) {
        const mid = (lo + hi) >> 1;
        if (x < spans[mid][0]) hi = mid - 1;
        else if (x > spans[mid][1]) lo = mid + 1;
        else return true;
      }
      return false;
    };

    // Нормировка: важна не громкость сама по себе, а «громче или тише
    // обычного». Медиана и среднее отклонение устойчивы к одному всплеску.
    const sorted = box.v.slice().sort((a, b) => a - b);
    const median = sorted[sorted.length >> 1];
    let spread = 0;
    for (let i = 0; i < count; i++) spread += Math.abs(box.v[i] - median);
    spread /= count;
    if (!(spread > 0.004)) {                       // ровная стена звука
      if (span > this.AUTO_MAX) box.done = true;
      return;
    }
    const z = new Float32Array(count);
    for (let i = 0; i < count; i++) {
      z[i] = Math.max(-2, Math.min(2, (box.v[i] - median) / spread));
    }

    // Время текста для каждого замера считаем один раз: внутри перебора
    // это тысячи лишних вызовов rate()/offset() на каждый шаг.
    const at = new Float64Array(count);
    for (let i = 0; i < count; i++) at[i] = this.clock(box.t[i]);

    const score = shift => {
      let sum = 0;
      for (let i = 0; i < count; i++) sum += covers(at[i] + shift) ? z[i] : -z[i];
      return sum / count;
    };

    // В окне должны быть и пение, и пауза: иначе сравнивать не с чем.
    let voiced = 0;
    for (let i = 0; i < count; i++) if (covers(at[i])) voiced++;
    const part = voiced / count;
    if (part < 0.1 || part > 0.95) {
      if (span > this.AUTO_MAX) box.done = true;
      return;
    }

    // Сначала грубо, шагом в полсекунды, потом точно вокруг победителя:
    // полный перебор с мелким шагом занял бы заметную часть кадра.
    //
    // Куплеты и припевы повторяются, поэтому у сдвига бывают двойники: сдвиг
    // на целую строфу совпадает с разметкой почти так же хорошо. Из близких
    // по качеству вариантов берём самый маленький — настоящее расхождение
    // почти всегда меньше, чем «ещё один куплет».
    const TIE = 0.02;
    const sweep = [];
    const pick = (from, to, step, keep) => {
      const found = [];
      let top = -Infinity;
      for (let x = from; x <= to + 1e-9; x += step) {
        const value = score(x);
        found.push([Math.round(x * 100) / 100, value]);
        if (keep) sweep.push(value);
        if (value > top) top = value;
      }
      let at = 0, value = -Infinity;
      for (const [x, got] of found) {
        if (got < top - TIE) continue;
        if (Math.abs(x) < Math.abs(at) - 1e-9 || value === -Infinity) { at = x; value = got; }
      }
      return [at, value];
    };

    const here = score(0);
    let [shift, best] = pick(-range, range, 0.5, true);
    if (shift) {
      const [fine, got] = pick(shift - 0.5, shift + 0.5, this.AUTO_STEP, false);
      if (got >= best - TIE) { shift = Math.round(fine * 20) / 20; best = got; }
    }

    // Насколько находка выделяется среди всех проверенных сдвигов. У
    // настоящего попадания пик острый и одинокий; если же в звуке просто
    // есть свой ритм, «хорошие» сдвиги находятся где угодно — такую находку
    // принимать нельзя, иначе текст уедет на ровном месте.
    let mean = 0;
    for (const value of sweep) mean += value;
    mean /= sweep.length;
    let spreadScore = 0;
    for (const value of sweep) spreadScore += (value - mean) * (value - mean);
    spreadScore = Math.sqrt(spreadScore / sweep.length);
    const sharp = spreadScore > 1e-6 ? (best - mean) / spreadScore : 0;

    if (Math.abs(shift) < 0.3 || best - here < this.AUTO_GAIN || best < 0.12
        || sharp < 3.5) {
      // Пока непонятно — слушаем дальше; совсем глухо, значит текст чужой.
      if (span <= this.AUTO_MAX) return;
      box.done = true;
      if (here < 0.04 && best - here < this.AUTO_GAIN) this.wrongRecord();
      return;
    }

    this.result42={accepted:true,shift,confidence:sharp};return;
    const value = Math.round(((+this.offsets[this.trackId] || 0) + shift) * 20) / 20;
    if (Math.abs(value) < 0.005) delete this.offsets[this.trackId];
    else this.offsets[this.trackId] = value;
    this.autoResults = this.autoResults || {}; this.autoResults[this.trackId] = { offset:value, confidence:sharp, signature:this.lyricSignature };
    api('/api/state',{method:'PUT',body:{key:'lyricsAutoResults',value:this.autoResults}}).catch(()=>{});
    this.saveOffsets();
    this.paintSync();
    this.resync();
    toast(t('Karaoke timing matched to the track') + ': ' +
          (value > 0 ? '+' : '') + value.toFixed(2) + 's');
  },

};
